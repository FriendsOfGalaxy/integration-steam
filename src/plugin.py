import asyncio
import logging
import platform
import subprocess
import ssl
import sys
import webbrowser
import time
from typing import Any, List, Optional, NewType, Dict

import certifi
from galaxy.api.plugin import Plugin, create_and_run_plugin
from galaxy.api.types import (
    Achievement, Authentication, Game, GameTime, LicenseInfo,
    LocalGame, LocalGameState, GameLibrarySettings, UserPresence, UserInfo, Subscription, SubscriptionGame
)
from galaxy.api.errors import (
    AuthenticationRequired, UnknownBackendResponse, InvalidCredentials, UnknownError, AccessDenied, BackendTimeout, BackendError
)
from galaxy.api.consts import Platform, LicenseType, SubscriptionDiscovery

from backend import SteamHttpClient, AuthenticatedHttpClient, UnfinishedAccountSetup
from client import (
    StateFlags, local_games_list, get_state_changes, get_client_executable,
    load_vdf, get_library_folders, get_app_manifests, app_id_from_manifest_path
)
from servers_cache import ServersCache
from presence import presence_from_user_info
from friends_cache import FriendsCache
from games_cache import GamesCache
from stats_cache import StatsCache
from user_info_cache import UserInfoCache
from times_cache import TimesCache
from persistent_cache_state import PersistentCacheState
from ownership_ticket_cache import OwnershipTicketCache
from protocol.websocket_client import WebSocketClient, UserActionRequired
from protocol.types import ProtoUserInfo
from registry_monitor import get_steam_registry_monitor
from uri_scheme_handler import is_uri_handler_installed
from version import __version__

from urllib import parse
from authentication import START_URI, END_URI, next_step_response

from contextlib import suppress
from http.cookies import SimpleCookie, Morsel


logger = logging.getLogger(__name__)

Timestamp = NewType('Timestamp', int)


def is_windows():
    return platform.system().lower() == "windows"

# TODO: Remove - Steamcommunity auth element
def dicts_to_morsels(cookies):
    morsels = []
    for cookie in cookies:
        name = cookie["name"]
        value = cookie["value"]
        m = Morsel()
        m.set(name, value, value)
        m["domain"] = cookie.get("domain", "")
        m["path"] = cookie.get("path", "")
        morsels.append(m)
    return morsels

NO_AVATAR_SET = '0000000000000000000000000000000000000000'
AVATAR_URL_PREFIX = 'https://steamcdn-a.akamaihd.net/steamcommunity/public/images/avatars/'
AVATAR_URL_SUFIX = '_full.jpg'
DEFAULT_AVATAR = 'https://steamcdn-a.akamaihd.net/steamcommunity/public/images/avatars/fe/fef49e7fa7e1997310d705b2a6158ff8dc1cdfeb_full.jpg'
STEAMCOMMUNITY_PROFILE_LINK = 'https://steamcommunity.com/profiles/'

COOLDOWN_TIME = 5


# TODO: Remove - Steamcommunity auth element
def morsels_to_dicts(morsels):
    cookies = []
    for morsel in morsels:
        cookie = {
            "name": morsel.key,
            "value": morsel.value,
            "domain": morsel["domain"],
            "path": morsel["path"]
        }
        cookies.append(cookie)
    return cookies


# TODO: Remove - Steamcommunity auth element
def parse_stored_cookies(cookies):
    if isinstance(cookies, dict):
        cookies = [{"name": key, "value": value} for key, value in cookies.items()]
    return dicts_to_morsels(cookies)


def galaxy_user_info_from_user_info(user_id, user_info):
    avatar_url = user_info.avatar_hash.hex()
    if avatar_url == NO_AVATAR_SET:
        avatar_url = DEFAULT_AVATAR
    else:
        avatar_url = AVATAR_URL_PREFIX + avatar_url[0:2] + '/' + avatar_url + AVATAR_URL_SUFIX
    profile_link = STEAMCOMMUNITY_PROFILE_LINK + user_id
    return UserInfo(user_id,
                 user_info.name,
                 avatar_url,
                 profile_link)


class SteamPlugin(Plugin):
    def __init__(self, reader, writer, token):
        super().__init__(Platform.Steam, __version__, reader, writer, token)
        self._regmon = get_steam_registry_monitor()
        self._local_games_cache: Optional[List[LocalGame]] = None
        self._ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self._ssl_context.load_verify_locations(certifi.where())
        self._http_client = AuthenticatedHttpClient()
        self._client = SteamHttpClient(self._http_client)
        self._persistent_storage_state = PersistentCacheState()
        self._friends_cache = FriendsCache()
        self._games_cache = GamesCache()
        self._translations_cache = dict()
        self._stats_cache = StatsCache()
        self._user_info_cache = UserInfoCache()
        self._times_cache = TimesCache()

        # waits for persistent cache to initialize
        self._steam_client = None
        self._steam_client_run_task = None

        self._tags_semaphore = asyncio.Semaphore(5)

        self._library_settings_import_iterator = 0
        self._last_launch: Timestamp = 0

        self._update_local_games_task = asyncio.create_task(asyncio.sleep(0))
        self._update_owned_games_task = asyncio.create_task(asyncio.sleep(0))
        self._pushing_cache_task = asyncio.create_task(asyncio.sleep(0))
        self._owned_games_parsed = None

        self._auth_data = None

        async def user_presence_update_handler(user_id: str, proto_user_info: ProtoUserInfo):
            self.update_user_presence(user_id, await presence_from_user_info(proto_user_info, self._translations_cache))

        self._friends_cache.updated_handler = user_presence_update_handler

    def handshake_complete(self):
        servers_cache = ServersCache(self._client, self._ssl_context, self.persistent_cache, self._persistent_storage_state)
        ownership_ticket_cache = OwnershipTicketCache(self.persistent_cache, self._persistent_storage_state)
        self._steam_client = WebSocketClient(
            self._client, self._ssl_context, servers_cache, self._friends_cache, self._games_cache,
            self._translations_cache, self._stats_cache, self._times_cache, self._user_info_cache,
            ownership_ticket_cache
        )

    # TODO: Remove - Steamcommunity auth element
    def _store_cookies(self, cookies):
        credentials = {
            "cookies": morsels_to_dicts(cookies)
        }
        self.store_credentials(credentials)

    # TODO: Remove - Steamcommunity auth element
    def _force_utc(self):
        cookies = SimpleCookie()
        cookies["timezoneOffset"] = "0,0"
        morsel = cookies["timezoneOffset"]
        morsel["domain"] = "steamcommunity.com"
        # override encoding (steam does not fallow RFC 6265)
        morsel.set("timezoneOffset", "0,0", "0,0")
        self._http_client.update_cookies(cookies)

    async def shutdown(self):
        self._regmon.close()
        await self._steam_client.close()
        await self._http_client.close()
        await self._steam_client.wait_closed()

        with suppress(asyncio.CancelledError):
            self._update_local_games_task.cancel()
            self._update_owned_games_task.cancel()
            self._pushing_cache_task.cancel()
            await self._update_local_games_task
            await self._update_owned_games_task
            await self._pushing_cache_task

    async def _authenticate(self, username=None, password=None, two_factor=None):
        if two_factor:
            return await self._steam_client.communication_queues['websocket'].put({'password': password, 'two_factor': two_factor})
        if not username or not password:
            raise UnknownBackendResponse()
        self._user_info_cache.account_username = username
        await self._steam_client.communication_queues['websocket'].put({'password': password})

    # TODO: Remove - Steamcommunity auth element
    async def _do_steamcommunity_auth(self, morsels):
        cookies = [(morsel.key, morsel) for morsel in morsels]

        self._http_client.update_cookies(cookies)
        self._http_client.set_cookies_updated_callback(self._store_cookies)
        self._force_utc()

        try:
            profile_url = await self._client.get_profile()
        except UnknownBackendResponse:
            raise InvalidCredentials()

        async def set_profile_data():
            try:
                await self._client.get_authentication_data()
                steam_id, login = await self._client.get_profile_data(profile_url)
                self._user_info_cache.account_username = login
                self._user_info_cache.old_flow = True
                self._user_info_cache.steam_id = steam_id
                self.create_task(self._steam_client.run(), "Run WebSocketClient")
                return steam_id, login
            except AccessDenied:
                raise InvalidCredentials()

        try:
            steam_id, login = await set_profile_data()
        except UnfinishedAccountSetup:
            await self._client.setup_steam_profile(profile_url)
            steam_id, login = await set_profile_data()

        self._http_client.set_auth_lost_callback(self.lost_authentication)

        if "steamRememberLogin" in (cookie[0] for cookie in cookies):
            logging.debug("Remember login cookie present")
        else:
            logging.debug("Remember login cookie not present")

        return Authentication(steam_id, login)

    async def cancel_task(self, task):
        try:
            task.cancel()
            await task
        except asyncio.CancelledError:
            pass

    async def authenticate(self, stored_credentials=None):
        if not stored_credentials:
            self.create_task(self._steam_client.run(), "Run WebSocketClient")
            return next_step_response(START_URI.LOGIN, END_URI.LOGIN_FINISHED)
        # TODO remove at some point, old refresh flow
        cookies = stored_credentials.get("cookies", [])
        if cookies:
            morsels = parse_stored_cookies(cookies)
            return await self._do_steamcommunity_auth(morsels)

        self._user_info_cache.from_dict(stored_credentials)
        if 'games' in self.persistent_cache:
            self._games_cache.loads(self.persistent_cache['games'])

        steam_run_task = self.create_task(self._steam_client.run(), "Run WebSocketClient")
        connection_timeout = 120
        try:
            await asyncio.wait_for(self._user_info_cache.initialized.wait(), connection_timeout)
        except asyncio.TimeoutError:
            try:
                self.raise_websocket_errors()
            except BackendError as e:
                logging.info(f"Unable to keep connection with steam backend {repr(e)}")
                raise
            except Exception as e:
                logging.info(f"Internal websocket exception caught during auth {repr(e)}")
                raise
            else:
                logging.info(f"Failed to initialize connection with steam client within {connection_timeout} seconds")
                raise BackendTimeout()
            finally:
                await self.cancel_task(steam_run_task)

        self.store_credentials(self._user_info_cache.to_dict())
        return Authentication(self._user_info_cache.steam_id, self._user_info_cache.persona_name)

    async def _get_websocket_auth_step(self):
        try:
            result = await asyncio.wait_for(self._steam_client.communication_queues['plugin'].get(), 60)
            result = result['auth_result']
        except asyncio.TimeoutError:
            self.raise_websocket_errors()
            raise BackendTimeout()
        return result

    async def _handle_login_finished(self, credentials):
        parsed_url = parse.urlsplit(credentials['end_uri'])

        params = parse.parse_qs(parsed_url.query)
        if 'username' not in params or 'password' not in params:
            return next_step_response(START_URI.LOGIN_FAILED, END_URI.LOGIN_FINISHED)

        username = params['username'][0]
        password = params['password'][0]
        self._user_info_cache.account_username = username
        self._auth_data = [username, password]
        await self._steam_client.communication_queues['websocket'].put({'password': password})
        result = await self._get_websocket_auth_step()
        if result == UserActionRequired.NoActionRequired:
            self._auth_data = None
            self.store_credentials(self._user_info_cache.to_dict())
            return Authentication(self._user_info_cache.steam_id, self._user_info_cache.persona_name)
        if result == UserActionRequired.EmailTwoFactorInputRequired:
            return next_step_response(START_URI.TWO_FACTOR_MAIL, END_URI.TWO_FACTOR_MAIL_FINISHED)
        if result == UserActionRequired.PhoneTwoFactorInputRequired:
            return next_step_response(START_URI.TWO_FACTOR_MOBILE, END_URI.TWO_FACTOR_MOBILE_FINISHED)
        else:
            return next_step_response(START_URI.LOGIN_FAILED, END_URI.LOGIN_FINISHED)

    async def _handle_two_step(self, params, fail, finish):
        if 'code' not in params:
            return next_step_response(fail, finish)

        two_factor = params['code'][0]
        await self._steam_client.communication_queues['websocket'].put(
            {'password': self._auth_data[1], 'two_factor': two_factor})
        result = await self._get_websocket_auth_step()
        logger.info(f'2fa result {result}')
        if result != UserActionRequired.NoActionRequired:
            return next_step_response(fail, finish)
        else:
            self._auth_data = None
            self.store_credentials(self._user_info_cache.to_dict())
            return Authentication(self._user_info_cache.steam_id, self._user_info_cache.persona_name)

    async def _handle_two_step_mobile_finished(self, credentials):
        parsed_url = parse.urlsplit(credentials['end_uri'])
        params = parse.parse_qs(parsed_url.query)
        return await self._handle_two_step(params, START_URI.TWO_FACTOR_MOBILE_FAILED, END_URI.TWO_FACTOR_MOBILE_FINISHED)

    async def _handle_two_step_email_finished(self, credentials):
        parsed_url = parse.urlsplit(credentials['end_uri'])
        params = parse.parse_qs(parsed_url.query)

        if 'resend' in params:
            await self._steam_client.communication_queues['websocket'].put({'password': self._auth_data[1]})
            await self._get_websocket_auth_step() # Clear the queue
            return next_step_response(START_URI.TWO_FACTOR_MAIL, END_URI.TWO_FACTOR_MAIL_FINISHED)

        return await self._handle_two_step(params, START_URI.TWO_FACTOR_MAIL_FAILED, END_URI.TWO_FACTOR_MAIL_FINISHED)

    async def pass_login_credentials(self, step, credentials, cookies):
        if 'login_finished' in credentials['end_uri']:
            return await self._handle_login_finished(credentials)
        if 'two_factor_mobile_finished' in credentials['end_uri']:
            return await self._handle_two_step_mobile_finished(credentials)
        if 'two_factor_mail_finished' in credentials['end_uri']:
            return await self._handle_two_step_email_finished(credentials)

    async def get_owned_games(self):
        if self._user_info_cache.steam_id is None:
            raise AuthenticationRequired()

        await self._games_cache.wait_ready(90)
        owned_games = []
        self._games_cache.add_game_lever = True

        try:
            temp_title = None
            async for app in self._games_cache.get_owned_games():
                if str(app.appid) == "292030":
                    temp_title = app.title
                owned_games.append(
                    Game(
                        str(app.appid),
                        app.title,
                        [],
                        LicenseInfo(LicenseType.SinglePurchase, None)
                    )
                )

            if temp_title:
                dlcs = []
                async for dlc in self._games_cache.get_dlcs():
                    dlcs.append(str(dlc.appid))
                if "355880" in dlcs or ("378648" in dlcs and "378649" in dlcs):
                    owned_games.append(Game(
                        "499450",
                        temp_title,
                        [],
                        LicenseInfo(LicenseType.SinglePurchase, None)
                    ))

        except (KeyError, ValueError):
            logger.exception("Can not parse backend response")
            raise UnknownBackendResponse()


        finally:
            self._owned_games_parsed = True
        self.persistent_cache['games'] = self._games_cache.dump()
        self._persistent_storage_state.modified = True

        return owned_games

    async def prepare_achievements_context(self, game_ids: List[str]) -> Any:
        if self._user_info_cache.steam_id is None:
            raise AuthenticationRequired()

        if not self._stats_cache.import_in_progress:
            await self._steam_client.refresh_game_stats(game_ids.copy())
        else:
            logger.info("Game stats import already in progress")
        await self._stats_cache.wait_ready(10 * 60) # Don't block future imports in case we somehow don't receive one of the responses
        logger.info("Finished achievements context prepare")

    async def get_unlocked_achievements(self, game_id: str, context: Any) -> List[Achievement]:
        logger.info(f"Asked for achievs for {game_id}")
        game_stats = self._stats_cache.get(game_id)
        achievements = []
        if game_stats:
            if 'achievements' not in game_stats:
                return []
            for achievement in game_stats['achievements']:

                # Fix for trailing whitespace in some achievement names which resulted in achievements not matching with website data
                achi_name = achievement['name']
                achi_name = achi_name.strip()
                if not achi_name:
                    achi_name = achievement['name']

                achievements.append(Achievement(achievement['unlock_time'], achievement_id=None, achievement_name=achi_name))
        return achievements

    async def prepare_game_times_context(self, game_ids: List[str]) -> Any:
        if self._user_info_cache.steam_id is None:
            raise AuthenticationRequired()

        if not self._times_cache.import_in_progress:
            await self._steam_client.refresh_game_times()
        else:
            logger.info("Game stats import already in progress")
        await self._times_cache.wait_ready(10 * 60) # Don't block future imports in case we somehow don't receive one of the responses
        logger.info("Finished game times context prepare")

    async def get_game_time(self, game_id: str, context: Dict[int, int]) -> GameTime:
        time_played = self._times_cache.get(game_id, {}).get('time_played')
        last_played = self._times_cache.get(game_id, {}).get('last_played')
        if last_played == 86400:
            last_played = None
        return GameTime(game_id, time_played, last_played)

    async def prepare_game_library_settings_context(self, game_ids: List[str]) -> Any:
        if self._user_info_cache.steam_id is None:
            raise AuthenticationRequired()

        return await self._steam_client.retrieve_collections()

    async def get_game_library_settings(self, game_id: str, context: Any) -> GameLibrarySettings:
        if not context:
            return GameLibrarySettings(game_id, None, None)
        else:
            game_in_collections = []
            hidden = False
            for collection_name in context:
                if int(game_id) in context[collection_name]:
                    if collection_name.lower() == 'hidden':
                        hidden = True
                    else:
                        game_in_collections.append(collection_name)

            return GameLibrarySettings(game_id, game_in_collections, hidden)

    async def get_friends(self):
        if self._user_info_cache.steam_id is None:
            raise AuthenticationRequired()

        friends_ids = await self._steam_client.get_friends()
        friends_infos = await self._steam_client.get_friends_info(friends_ids)
        friends_nicknames = await self._steam_client.get_friends_nicknames()

        friends = []
        for friend_id in friends_infos:
            friend = galaxy_user_info_from_user_info(str(friend_id), friends_infos[friend_id])
            if str(friend_id) in friends_nicknames:
                friend.user_name += f" ({friends_nicknames[friend_id]})"
            friends.append(friend)
        return friends

    async def prepare_user_presence_context(self, user_ids: List[str]) -> Any:
        return await self._steam_client.get_friends_info(user_ids)

    async def get_user_presence(self, user_id: str, context: Any) -> UserPresence:
        user_info = context.get(user_id)
        if user_info is None:
            raise UnknownError(
                "User {} not in friend list (plugin only supports fetching presence for friends)".format(user_id)
            )
        return await presence_from_user_info(user_info, self._translations_cache)

    async def _update_owned_games(self):
        new_games = self._games_cache.consume_added_games()
        if not new_games:
            return

        self.persistent_cache['games'] = self._games_cache.dump()
        self._persistent_storage_state.modified = True

        for i, game in enumerate(new_games):
            self.add_game(Game(game.appid, game.title, [], license_info=LicenseInfo(LicenseType.SinglePurchase)))
            if i % 50 == 49:
                await asyncio.sleep(5)  # give Galaxy a breath in case of adding thousands games

    def raise_websocket_errors(self):
        try:
            result = self._steam_client.communication_queues['errors'].get_nowait()
            if result and isinstance(result, Exception):
                raise result
        except asyncio.queues.QueueEmpty:
            pass

    def tick(self):
        if self._local_games_cache is not None and self._update_local_games_task.done() and self._regmon.is_updated():
            self._update_local_games_task = asyncio.create_task(self._update_local_games())

        if self._update_owned_games_task.done() and self._owned_games_parsed:
            self._update_owned_games_task = asyncio.create_task(self._update_owned_games())

        if self._pushing_cache_task.done() and self._persistent_storage_state.modified:
            self._pushing_cache = asyncio.create_task(self._push_cache())

        if self._user_info_cache.changed:
            self.store_credentials(self._user_info_cache.to_dict())

        if self._user_info_cache.initialized.is_set():
            self.raise_websocket_errors()

    async def _push_cache(self):
        self.push_cache()
        self._persistent_storage_state.modified = False
        await asyncio.sleep(COOLDOWN_TIME)  # lower pushing cache rate to do not clog socket in case of big cache

    async def _update_local_games(self):
        loop = asyncio.get_running_loop()
        new_list = await loop.run_in_executor(None, local_games_list)
        notify_list = get_state_changes(self._local_games_cache, new_list)
        self._local_games_cache = new_list
        for game in notify_list:
            if LocalGameState.Running in game.local_game_state:
                self._last_launch = time.time()
            self.update_local_game_status(game)
        await asyncio.sleep(COOLDOWN_TIME)

    async def get_local_games(self):
        loop = asyncio.get_running_loop()
        self._local_games_cache = await loop.run_in_executor(None, local_games_list)
        return self._local_games_cache

    @staticmethod
    def _steam_command(command, game_id):
        if game_id == "499450":
            game_id = "292030"
        if is_uri_handler_installed("steam"):
            webbrowser.open("steam://{}/{}".format(command, game_id))
        else:
            webbrowser.open("https://store.steampowered.com/about/")

    async def launch_game(self, game_id):
        SteamPlugin._steam_command("launch", game_id)

    async def install_game(self, game_id):
        SteamPlugin._steam_command("install", game_id)

    async def uninstall_game(self, game_id):
        SteamPlugin._steam_command("uninstall", game_id)

    async def get_subscriptions(self) -> List[Subscription]:
        if not self._owned_games_parsed:
            await self._games_cache.wait_ready(90)
        any_shared_game = False
        async for item in self._games_cache.get_shared_games():
            any_shared_game = True
            break
        return [Subscription("Family Sharing", any_shared_game, None, SubscriptionDiscovery.AUTOMATIC)]

    async def get_subscription_games(self, subscription_name: str, context: Any):
        games = []
        async for game in self._games_cache.get_shared_games():
            games.append(SubscriptionGame(game_id=str(game.appid), game_title=game.title))
        yield games

    async def prepare_local_size_context(self, game_ids: List[str]) -> Dict[str, str]:
        library_folders = get_library_folders()
        app_manifests = list(get_app_manifests(library_folders))
        return {
            app_id_from_manifest_path(path): path
            for path in app_manifests
        }

    async def get_local_size(self, game_id: str, context: Dict[str, str]) -> Optional[int]:
        try:
            manifest_path = context[game_id]
        except KeyError:  # not installed
            return 0
        try:
            manifest = load_vdf(manifest_path)
            app_state = manifest['AppState']
            state_flags = StateFlags(int(app_state['StateFlags']))
            if StateFlags.FullyInstalled in state_flags:
                return int(app_state['SizeOnDisk'])
            else:  # as SizeOnDisk is 0
                return int(app_state['BytesDownloaded'])
        except Exception as e:
            logger.warning("Cannot parse SizeOnDisk in %s: %r", manifest_path, e)
            return None

    async def shutdown_platform_client(self) -> None:
        launch_debounce_time = 30
        if time.time() < self._last_launch + launch_debounce_time:
            # workaround for quickly closed game (Steam sometimes dumps false positive just after a launch)
            logging.info('Ignoring shutdown request because game was launched a moment ago')
            return
        if is_windows():
            exe = get_client_executable()
            if exe is None:
                return
            cmd = '"{}" -shutdown -silent'.format(exe)
        else:
            cmd = "osascript -e 'quit app \"Steam\"'"
        logger.debug("Running command '%s'", cmd)
        process = await asyncio.create_subprocess_shell(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await process.communicate()


def main():
    create_and_run_plugin(SteamPlugin, sys.argv)


if __name__ == "__main__":
    main()
