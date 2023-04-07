import asyncio
import logging
import ssl
from contextlib import suppress
from distutils.util import strtobool
from typing import Callable, List, Any, Dict, Union
from urllib import parse

from galaxy.api.errors import (
    AuthenticationRequired,
    UnknownBackendResponse,
    UnknownError,
    BackendTimeout,
)
from galaxy.api.types import (
    Game,
    LicenseInfo,
    LicenseType,
    UserInfo,
    UserPresence,
    Subscription,
    SubscriptionDiscovery,
    SubscriptionGame,
    Achievement,
    GameLibrarySettings,
    GameTime,
    Authentication, NextStep,
)

from backend_interface import BackendInterface
from http_client import HttpClient
from persistent_cache_state import PersistentCacheState
from user_profile import UserProfileChecker, ProfileIsNotPublic, ProfileDoesNotExist, NotPublicGameDetailsOrUserHasNoGames
from steam_network.authentication import StartUri, EndUri, next_step_response
from steam_network.friends_cache import FriendsCache
from steam_network.games_cache import GamesCache
from steam_network.local_machine_cache import LocalMachineCache
from steam_network.ownership_ticket_cache import OwnershipTicketCache
from steam_network.presence import presence_from_user_info
from steam_network.protocol.types import ProtoUserInfo  # TODO accessing inner module
from steam_network.stats_cache import StatsCache
from steam_network.steam_http_client import SteamHttpClient
from steam_network.times_cache import TimesCache
from steam_network.user_info_cache import UserInfoCache
from steam_network.websocket_client import WebSocketClient, UserActionRequired
from steam_network.websocket_list import WebSocketList
from steam_network.w3_hack import (
    WITCHER_3_DLCS_APP_IDS,
    WITCHER_3_GOTY_APP_ID,
    WITCHER_3_GOTY_TITLE,
    does_witcher_3_dlcs_set_resolve_to_GOTY
)

logger = logging.getLogger(__name__)


GAME_CACHE_IS_READY_TIMEOUT = 90
USER_INFO_CACHE_INITIALIZED_TIMEOUT = 30

GAME_DOES_NOT_SUPPORT_LAST_PLAYED_VALUE = 86400
STEAMCOMMUNITY_PROFILE_BASE_URL = "https://steamcommunity.com/profiles/"
AVATAR_URL_TEMPLATE = "https://steamcdn-a.akamaihd.net/steamcommunity/public/images/avatars/{}/{}_full.jpg"
NO_AVATAR_SET = "0000000000000000000000000000000000000000"
DEFAULT_AVATAR_HASH = "fef49e7fa7e1997310d705b2a6158ff8dc1cdfeb"


def avatar_url_from_avatar_hash(a_hash: str):
    if a_hash == NO_AVATAR_SET:
        a_hash = DEFAULT_AVATAR_HASH
    return AVATAR_URL_TEMPLATE.format(a_hash[0:2], a_hash)


class SteamNetworkBackend(BackendInterface):
    def __init__(
        self,
        *,
        http_client: HttpClient,
        user_profile_checker: UserProfileChecker,
        ssl_context: ssl.SSLContext,
        persistent_storage_state: PersistentCacheState,
        persistent_cache: Dict[str, Any],
        update_user_presence: Callable[[UserPresence], None],
        store_credentials: Callable[[Dict[str, Any]], None],
        add_game: Callable[[Game], None],
    ) -> None:

        self._add_game = add_game
        self._persistent_cache = persistent_cache
        self._persistent_storage_state = persistent_storage_state
        self._user_profile_checker = user_profile_checker

        self._store_credentials = store_credentials
        self._user_info_cache = UserInfoCache()

        self._games_cache = GamesCache()
        self._translations_cache = dict()
        self._stats_cache = StatsCache()
        self._times_cache = TimesCache()
        self._friends_cache = FriendsCache()

        async def user_presence_update_handler(user_id: str, proto_user_info: ProtoUserInfo):
            update_user_presence(
                user_id,
                await presence_from_user_info(proto_user_info, self._translations_cache),
            )

        self._friends_cache.updated_handler = user_presence_update_handler

        ownership_ticket_cache = OwnershipTicketCache(
            self._persistent_cache, self._persistent_storage_state
        )
        local_machine_cache = LocalMachineCache(
            self._persistent_cache, self._persistent_storage_state
        )

        steam_http_client = SteamHttpClient(http_client)
        self._websocket_client = WebSocketClient(
            WebSocketList(steam_http_client),
            ssl_context,
            self._friends_cache,
            self._games_cache,
            self._translations_cache,
            self._stats_cache,
            self._times_cache,
            self._user_info_cache,
            local_machine_cache,
            ownership_ticket_cache,
        )

        self._update_owned_games_task = asyncio.create_task(asyncio.sleep(0))
        self._owned_games_parsed = None
        self._auth_data = None
        
        self._load_persistent_cache()
    
    def _load_persistent_cache(self):
        if "games" in self._persistent_cache:
            self._games_cache.loads(self._persistent_cache["games"])
    
    def register_auth_lost_callback(self, callback: Callable):
        self._websocket_client.authentication_lost_handler = callback

    async def shutdown(self):
        await self._websocket_client.close()
        await self._websocket_client.wait_closed()

        await self._cancel_task(self._update_owned_games_task)
        await self._cancel_task(self._steam_run_task)

    async def _cancel_task(self, task):
        with suppress(asyncio.CancelledError):
            task.cancel()
            await task

    # periodic tasks

    async def _update_owned_games(self):
        new_games = self._games_cache.consume_added_games()
        if not new_games:
            return

        self._persistent_cache["games"] = self._games_cache.dump()
        self._persistent_storage_state.modified = True

        for i, game in enumerate(new_games):
            self._add_game(
                Game(
                    game.appid,
                    game.title,
                    [],
                    license_info=LicenseInfo(LicenseType.SinglePurchase),
                )
            )
            if i % 50 == 49:
                await asyncio.sleep(5)  # give Galaxy a breath in case of adding thousands games

    def tick(self):
        if self._update_owned_games_task.done() and self._owned_games_parsed:
            self._update_owned_games_task = asyncio.create_task(self._update_owned_games())

        if self._user_info_cache.changed:
            self._store_credentials(self._user_info_cache.to_dict())

    # authentication

    async def _get_websocket_auth_step(self):
        try:
            result = await asyncio.wait_for(
                self._websocket_client.communication_queues["plugin"].get(), 20
            )
            return result["auth_result"]
        except asyncio.TimeoutError:
            return UserActionRequired.NoActionRequired
            #raise BackendTimeout()

    async def pass_login_credentials(self, step, credentials, cookies):
        if "login_finished" in credentials["end_uri"]:
            return await self._handle_login_finished(credentials)
        if "two_factor_mobile_finished" in credentials["end_uri"]:
            return await self._handle_two_step_mobile_finished(credentials)
        if "two_factor_mail_finished" in credentials["end_uri"]:
            return await self._handle_two_step_email_finished(credentials)
        if "public_prompt_finished" in credentials["end_uri"]:
            return await self._handle_public_prompt_finished(credentials)

    async def _handle_login_finished(self, credentials):
        parsed_url = parse.urlsplit(credentials["end_uri"])

        params = parse.parse_qs(parsed_url.query)
        if "username" not in params or "password" not in params:
            return next_step_response(StartUri.LOGIN_FAILED, EndUri.LOGIN_FINISHED)

        username = params["username"][0]
        password = params["password"][0]
        self._user_info_cache.account_username = username
        self._auth_data = [username, password]
        await self._websocket_client.communication_queues["websocket"].put({"password": password})
        result = await self._get_websocket_auth_step()
        if result == UserActionRequired.NoActionRequired:
            self._auth_data = None
            self._store_credentials(self._user_info_cache.to_dict())
            return await self._check_public_profile()
        if result == UserActionRequired.EmailTwoFactorInputRequired:
            return next_step_response(StartUri.TWO_FACTOR_MAIL, EndUri.TWO_FACTOR_MAIL_FINISHED)
        if result == UserActionRequired.PhoneTwoFactorInputRequired:
            return next_step_response(StartUri.TWO_FACTOR_MOBILE, EndUri.TWO_FACTOR_MOBILE_FINISHED)
        else:
            return next_step_response(StartUri.LOGIN_FAILED, EndUri.LOGIN_FINISHED)

    async def _handle_two_step(self, params, fail, finish):
        if "code" not in params:
            return next_step_response(fail, finish)

        two_factor = params["code"][0]
        await self._websocket_client.communication_queues["websocket"].put(
            {"password": self._auth_data[1], "two_factor": two_factor}
        )
        result = await self._get_websocket_auth_step()
        logger.info(f"2fa result {result}")
        if result != UserActionRequired.NoActionRequired:
            return next_step_response(fail, finish)
        else:
            self._auth_data = None
            self._store_credentials(self._user_info_cache.to_dict())
            #return await self._check_public_profile()
            return Authentication(self._user_info_cache.steam_id, self._user_info_cache.persona_name)

    async def _handle_two_step_mobile_finished(self, credentials):
        parsed_url = parse.urlsplit(credentials["end_uri"])
        params = parse.parse_qs(parsed_url.query)
        return await self._handle_two_step(
            params, StartUri.TWO_FACTOR_MOBILE_FAILED, EndUri.TWO_FACTOR_MOBILE_FINISHED
        )

    async def _handle_two_step_email_finished(self, credentials):
        parsed_url = parse.urlsplit(credentials["end_uri"])
        params = parse.parse_qs(parsed_url.query)

        if "resend" in params:
            await self._websocket_client.communication_queues["websocket"].put(
                {"password": self._auth_data[1]}
            )
            await self._get_websocket_auth_step()  # Clear the queue
            return next_step_response(StartUri.TWO_FACTOR_MAIL, EndUri.TWO_FACTOR_MAIL_FINISHED)

        return await self._handle_two_step(
            params, StartUri.TWO_FACTOR_MAIL_FAILED, EndUri.TWO_FACTOR_MAIL_FINISHED
        )

    async def _handle_public_prompt_finished(self, credentials):
        parsed_url = parse.urlsplit(credentials["end_uri"])
        params = dict(parse.parse_qsl(parsed_url.query))
        user_wants_pp_fallback = strtobool(params.get("public_profile_fallback"))
        if user_wants_pp_fallback:
            return await self._check_public_profile()
        return Authentication(self._user_info_cache.steam_id, self._user_info_cache.persona_name)

    async def _check_public_profile(self) -> Union[Authentication, NextStep]:
        try:
            await self._user_profile_checker.check_is_public_by_steam_id(self._user_info_cache.steam_id)
        except ProfileIsNotPublic:
            logger.debug(f"Profile with Steam64 ID: `{self._user_info_cache.steam_id}` is not public")
            return next_step_response(StartUri.PP_PROMPT__PROFILE_IS_NOT_PUBLIC, EndUri.PUBLIC_PROMPT_FINISHED)
        except NotPublicGameDetailsOrUserHasNoGames:
            logger.debug(f"Profile with Steam64 ID: `{self._user_info_cache.steam_id}` has private games library or has no games")
            return next_step_response(StartUri.PP_PROMPT__NOT_PUBLIC_GAME_DETAILS_OR_USER_HAS_NO_GAMES, EndUri.PUBLIC_PROMPT_FINISHED)
        except ProfileDoesNotExist:
            logger.warning(f"Profile with provided Steam64 ID: `{self._user_info_cache.steam_id}` does not exist")
            raise UnknownBackendResponse()
        except ValueError:
            logger.warning(f"Incorrect provided Steam64 ID: `{self._user_info_cache.steam_id}`")
            raise UnknownBackendResponse()
        except Exception:
            return next_step_response(StartUri.PP_PROMPT__UNKNOWN_ERROR, EndUri.PUBLIC_PROMPT_FINISHED)
        else:
            return Authentication(
                self._user_info_cache.steam_id, self._user_info_cache.persona_name
            )

    async def authenticate(self, stored_credentials=None):
        if stored_credentials is None:
            self._steam_run_task = asyncio.create_task(self._websocket_client.run())
            return next_step_response(StartUri.LOGIN, EndUri.LOGIN_FINISHED)
        return await self._authenticate_with_stored_credentials(stored_credentials)
    
    async def _authenticate_with_stored_credentials(self, stored_credentials):
        self._user_info_cache.from_dict(stored_credentials)

        self._steam_run_task = asyncio.create_task(self._websocket_client.run())
        user_info_ready_task = asyncio.create_task(self._user_info_cache.initialized.wait())

        done, _ = await asyncio.wait(
            {self._steam_run_task, user_info_ready_task},
            timeout = USER_INFO_CACHE_INITIALIZED_TIMEOUT,
            return_when = asyncio.FIRST_COMPLETED
        )
        
        if user_info_ready_task in done:
            self._store_credentials(self._user_info_cache.to_dict())
            return Authentication(self._user_info_cache.steam_id, self._user_info_cache.persona_name)
        elif self._steam_run_task in done:
            try:
                await self._steam_run_task   
            except Exception as e:
                logger.exception(f"Unable to authenticate to steam backend: {repr(e)}")
                raise
            else:
                raise UnknownError("Unexcpeted, silent websocket close.")
        else:
            logger.warning(
                f"Failed to login on steam server within {USER_INFO_CACHE_INITIALIZED_TIMEOUT} seconds."
            )
            await self._cancel_task(self._steam_run_task)
            raise BackendTimeout()

    # features implementation

    async def get_owned_games(self) -> List[Game]:
        if self._user_info_cache.steam_id is None:
            raise AuthenticationRequired()

        await self._games_cache.wait_ready(GAME_CACHE_IS_READY_TIMEOUT)
        self._games_cache.add_game_lever = True

        owned_games = []
        owned_witcher_3_dlcs = set()

        try:
            async for app in self._games_cache.get_owned_games():
                owned_games.append(
                    Game(
                        str(app.appid),
                        app.title,
                        [],
                        LicenseInfo(LicenseType.SinglePurchase, None),
                    )
                )
                if app.appid in WITCHER_3_DLCS_APP_IDS:
                    owned_witcher_3_dlcs.add(app.appid)

            if does_witcher_3_dlcs_set_resolve_to_GOTY(owned_witcher_3_dlcs):
                owned_games.append(
                    Game(
                        WITCHER_3_GOTY_APP_ID,
                        WITCHER_3_GOTY_TITLE,
                        [],
                        LicenseInfo(LicenseType.SinglePurchase, None),
                    )
                )

        except (KeyError, ValueError):
            logger.exception("Cannot parse backend response")
            raise UnknownBackendResponse()

        finally:
            self._owned_games_parsed = True

        self._persistent_cache["games"] = self._games_cache.dump()
        self._persistent_storage_state.modified = True

        return owned_games

    async def get_subscriptions(self) -> List[Subscription]:
        if not self._owned_games_parsed:
            await self._games_cache.wait_ready(90)
        any_shared_game = False
        async for _ in self._games_cache.get_shared_games():
            any_shared_game = True
            break
        return [
            Subscription(
                "Steam Family Sharing",
                any_shared_game,
                None,
                SubscriptionDiscovery.AUTOMATIC,
            )
        ]

    async def get_subscription_games(self, subscription_name: str, context: Any):
        games = []
        async for game in self._games_cache.get_shared_games():
            games.append(SubscriptionGame(game_id=str(game.appid), game_title=game.title))
        yield games

    async def prepare_achievements_context(self, game_ids: List[str]) -> Any:
        if self._user_info_cache.steam_id is None:
            raise AuthenticationRequired()

        if not self._stats_cache.import_in_progress:
            await self._websocket_client.refresh_game_stats(game_ids.copy())
        else:
            logger.info("Game stats import already in progress")
        await self._stats_cache.wait_ready(
            10 * 60
        )  # Don't block future imports in case we somehow don't receive one of the responses
        logger.info("Finished achievements context prepare")

    async def get_unlocked_achievements(self, game_id: str, context: Any) -> List[Achievement]:
        logger.info(f"Asked for achievs for {game_id}")
        game_stats = self._stats_cache.get(game_id)
        achievements = []
        if game_stats and "achievements" in game_stats:
            for achievement in game_stats["achievements"]:
                # Fix for trailing whitespace in some achievement names which resulted in achievements not matching with website data
                achievement_name = achievement["name"]
                achievement_name = achievement_name.strip()
                if not achievement_name:
                    achievement_name = achievement["name"]

                achievements.append(
                    Achievement(
                        achievement["unlock_time"],
                        achievement_id=None,
                        achievement_name=achievement_name,
                    )
                )
        return achievements

    async def prepare_game_times_context(self, game_ids: List[str]) -> Any:
        if self._user_info_cache.steam_id is None:
            raise AuthenticationRequired()

        if not self._times_cache.import_in_progress:
            await self._websocket_client.refresh_game_times()
        else:
            logger.info("Game stats import already in progress")
        await self._times_cache.wait_ready(
            10 * 60
        )  # Don't block future imports in case we somehow don't receive one of the responses
        logger.info("Finished game times context prepare")

    async def get_game_time(self, game_id: str, context: Dict[int, int]) -> GameTime:
        time_played = self._times_cache.get(game_id, {}).get("time_played")
        last_played = self._times_cache.get(game_id, {}).get("last_played")
        if last_played == GAME_DOES_NOT_SUPPORT_LAST_PLAYED_VALUE:
            last_played = None
        return GameTime(game_id, time_played, last_played)

    async def prepare_game_library_settings_context(self, game_ids: List[str]) -> Any:
        if self._user_info_cache.steam_id is None:
            raise AuthenticationRequired()

        return await self._websocket_client.retrieve_collections()

    async def get_game_library_settings(self, game_id: str, context: Any) -> GameLibrarySettings:
        if not context:
            return GameLibrarySettings(game_id, None, None)
        else:
            game_in_collections = []
            hidden = False
            for collection_name in context:
                if int(game_id) in context[collection_name]:
                    if collection_name.lower() == "hidden":
                        hidden = True
                    else:
                        game_in_collections.append(collection_name)

            return GameLibrarySettings(game_id, game_in_collections, hidden)

    async def get_friends(self):
        if self._user_info_cache.steam_id is None:
            raise AuthenticationRequired()

        friends_ids = await self._websocket_client.get_friends()
        friends_infos = await self._websocket_client.get_friends_info(friends_ids)
        friends_nicknames = await self._websocket_client.get_friends_nicknames()

        friends = []
        for friend_id in friends_infos:
            friend = self._galaxy_user_info_from_user_info(str(friend_id), friends_infos[friend_id])
            if str(friend_id) in friends_nicknames:
                friend.user_name += f" ({friends_nicknames[friend_id]})"
            friends.append(friend)
        return friends

    @staticmethod
    def _galaxy_user_info_from_user_info(user_id, user_info):
        avatar_url = avatar_url_from_avatar_hash(user_info.avatar_hash.hex())
        profile_link = STEAMCOMMUNITY_PROFILE_BASE_URL + user_id
        return UserInfo(user_id, user_info.name, avatar_url, profile_link)

    async def prepare_user_presence_context(self, user_ids: List[str]) -> Any:
        return await self._websocket_client.get_friends_info(user_ids)

    async def get_user_presence(self, user_id: str, context: Any) -> UserPresence:
        user_info = context.get(user_id)
        if user_info is None:
            raise UnknownError(
                "User {} not in friend list (plugin only supports fetching presence for friends)".format(
                    user_id
                )
            )
        return await presence_from_user_info(user_info, self._translations_cache)
