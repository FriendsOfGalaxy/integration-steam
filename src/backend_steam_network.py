import asyncio
import logging
import ssl
from contextlib import suppress
from typing import Callable, List, Any, Dict, Union, Coroutine, cast
from urllib import parse
from pprint import pformat

from asyncio import Task

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
from steam_network.authentication_cache import AuthenticationCache
from steam_network.friends_cache import FriendsCache
from steam_network.games_cache import GamesCache
from steam_network.local_machine_cache import LocalMachineCache
from steam_network.presence import presence_from_user_info
from steam_network.protocol.steam_types import ProtoUserInfo  # TODO accessing inner module
from steam_network.stats_cache import StatsCache
from steam_network.steam_http_client import SteamHttpClient
from steam_network.times_cache import TimesCache
from steam_network.user_info_cache import UserInfoCache
from steam_network.websocket_client import WebSocketClient
from steam_network.websocket_list import WebSocketList
from steam_network.w3_hack import (
    WITCHER_3_DLCS_APP_IDS,
    WITCHER_3_GOTY_APP_ID,
    WITCHER_3_GOTY_TITLE,
    does_witcher_3_dlcs_set_resolve_to_GOTY
)

from steam_network.utils import next_step_response_simple
from steam_network.enums import UserActionRequired, AuthCall, DisplayUriHelper, TwoFactorMethod

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
    def __init__(self, http_client: HttpClient, ssl_context: ssl.SSLContext, 
                 persistent_storage_state: PersistentCacheState, persistent_cache: Dict[str, Any], update_user_presence: Callable[[UserPresence], None], 
                 store_credentials: Callable[[Dict[str, Any]], None], add_game: Callable[[Game], None]):

        self._add_game : Callable[[Game], None] = add_game
        self._persistent_cache : Dict[str, Any] = persistent_cache
        self._persistent_storage_state : PersistentCacheState = persistent_storage_state

        self._store_credentials : Callable[[Dict[str, Any]], None] = store_credentials
        self._authentication_cache : AuthenticationCache = AuthenticationCache()
        self._user_info_cache : UserInfoCache = UserInfoCache()

        self._games_cache : GamesCache = GamesCache()
        self._translations_cache : Dict[int, str] = dict()
        self._stats_cache :StatsCache = StatsCache()
        self._times_cache : TimesCache = TimesCache()
        self._friends_cache : FriendsCache = FriendsCache()

        async def user_presence_update_handler(user_id: str, proto_user_info: ProtoUserInfo):
            update_user_presence(
                user_id,
                await presence_from_user_info(proto_user_info, self._translations_cache),
            )

        self._friends_cache.updated_handler : Callable[[str, ProtoUserInfo], Coroutine[Any, Any, None]] = user_presence_update_handler

        local_machine_cache : LocalMachineCache = LocalMachineCache(self._persistent_cache, self._persistent_storage_state)

        steam_http_client = SteamHttpClient(http_client)
        self._websocket_client = WebSocketClient(
            WebSocketList(steam_http_client),
            ssl_context,
            self._friends_cache,
            self._games_cache,
            self._translations_cache,
            self._stats_cache,
            self._times_cache,
            self._authentication_cache,
            self._user_info_cache,
            local_machine_cache,
        )

        self._update_owned_games_task : Task[None] = asyncio.create_task(asyncio.sleep(0))
        self._owned_games_parsed : bool = False
        
        self._load_persistent_cache()
    
    def _load_persistent_cache(self):
        if "games" in self._persistent_cache:
            self._games_cache.loads(self._persistent_cache["games"])

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

    async def _get_websocket_auth_step(self) -> UserActionRequired:
        try:
            result = await asyncio.wait_for(
                self._websocket_client.communication_queues["plugin"].get(), 60
            )
            logger.info("plugin received: " + pformat(result))
            return result["auth_result"]
        except asyncio.TimeoutError:
            raise BackendTimeout()

    def _get_mobile_confirm_kwargs(self, allowed_methods: Dict[TwoFactorMethod, str]):
        fallbackData = {}
        if len(allowed_methods) > 1:
            fallback_meth, fallback_message = allowed_methods[1]
        
            if (fallback_meth == TwoFactorMethod.PhoneCode):
                fallbackData["fallbackMethod"] = DisplayUriHelper.TWO_FACTOR_MOBILE.to_view_string()
                fallbackData["fallbackMsg"] = fallback_message
            elif (fallback_meth == TwoFactorMethod.EmailCode):
                fallbackData["fallbackMethod"] = DisplayUriHelper.TWO_FACTOR_MAIL.to_view_string()
                fallbackData["fallbackMsg"] = fallback_message

        return fallbackData

    async def pass_login_credentials(self, step, credentials: Dict[str, str], cookies):
        end_uri = credentials["end_uri"]

        if (DisplayUriHelper.LOGIN.EndUri() in end_uri):
            return await self._handle_login_finished(credentials)
        elif (DisplayUriHelper.TWO_FACTOR_MAIL.EndUri() in end_uri):
            return await self._handle_steam_guard(credentials, TwoFactorMethod.EmailCode, DisplayUriHelper.TWO_FACTOR_MAIL)
        elif (DisplayUriHelper.TWO_FACTOR_MOBILE.EndUri() in end_uri):
            return await self._handle_steam_guard(credentials, TwoFactorMethod.PhoneCode, DisplayUriHelper.TWO_FACTOR_MOBILE)
        elif (DisplayUriHelper.TWO_FACTOR_CONFIRM.EndUri() in end_uri):
            allowed_methods = self._authentication_cache.two_factor_allowed_methods
            fallback_data = self._get_mobile_confirm_kwargs(allowed_methods)

            return await self._handle_steam_guard_check(DisplayUriHelper.TWO_FACTOR_CONFIRM, True, **fallback_data) #go back to confirm. 
        else:
            logger.warning("Unexpected state in pass_login_credentials")
            raise UnknownBackendResponse()

    @staticmethod
    def sanitize_string(data : str) -> str:
        """Remove any characters steam silently strips, then trims it down to their max length.

        Steam appears to ignore all characters that it cannot handle, and trim it down to 64 legal characters.
        For whatever reason, they don't enforce this, they just silently ignore anything bad. This is our attempt to copy that behavior.
        """
        return (''.join([i if ord(i) < 128 else '' for i in data]))[:64]

    async def _handle_login_finished(self, credentials: Dict[str, str]) -> Union[NextStep, Authentication]:
        parsed_url = parse.urlsplit(credentials["end_uri"])
        params = parse.parse_qs(parsed_url.query)
        if ("password" not in params or "username" not in params):
            return next_step_response_simple(DisplayUriHelper.LOGIN, True)
        user = params["username"][0]
        pws = self.sanitize_string(params["password"][0])

        await self._websocket_client.communication_queues["websocket"].put({'mode': AuthCall.RSA_AND_LOGIN, 'username' : user, 'password' : pws })
        result = await self._get_websocket_auth_step()
        if (result == UserActionRequired.NoActionConfirmLogin):
            #we still don't have the 2FA Confirmation. that's actually required for NoAction, but instead of waiting for us to input 2FA, it immediately returns what we need. 
            return await self._handle_steam_guard_none()
        elif (result == UserActionRequired.TwoFactorRequired):
            allowed_methods = self._authentication_cache.two_factor_allowed_methods
            method, msg = allowed_methods[0]
            if (method == TwoFactorMethod.Nothing):
                return await self._handle_steam_guard_none()
            elif (method == TwoFactorMethod.PhoneCode):
                return next_step_response_simple(DisplayUriHelper.TWO_FACTOR_MOBILE)
            elif (method == TwoFactorMethod.EmailCode):
                return next_step_response_simple(DisplayUriHelper.TWO_FACTOR_MAIL)
            elif (method == TwoFactorMethod.PhoneConfirm):
                fallback_data = self._get_mobile_confirm_kwargs(allowed_methods)
                return next_step_response_simple(DisplayUriHelper.TWO_FACTOR_CONFIRM, False, message=msg, **fallback_data)
            else:
                raise UnknownBackendResponse()
        else:
            return next_step_response_simple(DisplayUriHelper.LOGIN, True)
        #result here should be password, or unathorized. 

    async def _handle_steam_guard(self, credentials: Dict[str, str], method: TwoFactorMethod, fallback: DisplayUriHelper) -> Union[NextStep, Authentication]:
        parsed_url: parse.SplitResult = parse.urlsplit(credentials["end_uri"])
        params = parse.parse_qs(parsed_url.query)
        if ("code" not in params):
            return next_step_response_simple(fallback, True)
        code = params["code"][0].strip()
        await self._websocket_client.communication_queues["websocket"].put({'mode': AuthCall.UPDATE_TWO_FACTOR, 'two-factor-code' : code, 'two-factor-method' : method })
        result = await self._get_websocket_auth_step()
        if (result == UserActionRequired.NoActionConfirmLogin):
            return await self._handle_steam_guard_check(fallback, False)
        elif (result == UserActionRequired.TwoFactorExpired):
            return next_step_response_simple(DisplayUriHelper.LOGIN, True, expired="true")
        elif (result == UserActionRequired.InvalidAuthData):
            return next_step_response_simple(fallback, True)
        else:
            raise UnknownBackendResponse()

    async def _handle_steam_guard_none(self) -> Authentication:
        result = await self._handle_2FA_PollOnce()
        if (result == UserActionRequired.NoActionRequired):
            return Authentication(self._user_info_cache.steam_id, self._user_info_cache.persona_name)
        elif result == UserActionRequired.NoActionConfirmToken:
            return await self._finish_auth_process()
        else:
            raise UnknownBackendResponse()

    async def _handle_steam_guard_check(self, fallback: DisplayUriHelper, is_confirm: bool, **kwargs:str) -> Union[NextStep, Authentication]:
        result = await self._handle_2FA_PollOnce(is_confirm)
        logger.info(f"steam guard check next action: {result.name}")
        if (result == UserActionRequired.NoActionRequired): #should never be hit. we need to confirm the token.
            return Authentication(self._user_info_cache.steam_id, self._user_info_cache.persona_name)
        elif (result == UserActionRequired.NoActionConfirmToken):
            return await self._finish_auth_process()
        elif(result == UserActionRequired.NoActionConfirmLogin or result == UserActionRequired.TwoFactorRequired):
            if (is_confirm):
                logger.info("Mobile Confirm did not complete. This is likely due to user error, but if not, this is something worth checking.")
            else:
                logger.info("Mobile code 2FA failed, likely expired. Could also be wrong code, as steam seems to give the same response.")
            return next_step_response_simple(fallback, True, **kwargs)
        elif (result == UserActionRequired.TwoFactorExpired):
            return next_step_response_simple(DisplayUriHelper.LOGIN, True, expired="true", **kwargs)
        else:
            raise UnknownBackendResponse()

    #in the case of confirm, this needs to be called directly, because the user clicks a button saying "i confirmed it on steam's end"
    #but, to handle edge cases (expired, they lied), we need to potentially display a page again. 
    async def _handle_2FA_PollOnce(self, is_confirm : bool = False) -> UserActionRequired:
        """ Poll the steam authentication to see if we are logged in yet, and return whatever action is required. 

        If the poll succeeds, but we aren't logged in yet (waiting on a code or mobile confirm), it returns UserActionRequired.NoActionConfirmLogin
        If the poll succeeds and we are logged in, it returns UserActionRequired.NoActionConfirmToken
        If the poll fails with the Result "Expired", returns UserActionRequired.TwoFactorExpired
        If the poll otherwise fails, it return UserActionRequired.InvalidAuthData
        """
        await self._websocket_client.communication_queues["websocket"].put({'mode': AuthCall.POLL_TWO_FACTOR, 'is-confirm' : is_confirm})

        #can return NoActionConfirmToken, NoActionConfirmLogin (poll succeeded, but we haven't logged in ye)
        return await self._get_websocket_auth_step()

    async def _finish_auth_process(self) -> Authentication:
        """ Essentially, call the classic Client.Login and get all the messages back we normally would. 


        """
        if (self._user_info_cache.is_initialized()):
            await self._websocket_client.communication_queues["websocket"].put({'mode': AuthCall.TOKEN})
            result = await self._get_websocket_auth_step()
            if (result != UserActionRequired.NoActionRequired):
                logger.warning("Unexpected Action Required after normal login. Nothing to fall back to")
                raise UnknownBackendResponse()
            else:
                return Authentication(self._user_info_cache.steam_id, self._user_info_cache.persona_name)
        else:
            logger.warning("User Info Cache not initialized after normal login. Unexpected")
            raise UnknownBackendResponse()

    async def authenticate(self, stored_credentials=None):
        self._steam_run_task = asyncio.create_task(self._websocket_client.run())
        if stored_credentials is None:
            return next_step_response_simple(DisplayUriHelper.LOGIN)
        else:
            return await self._authenticate_with_stored_credentials(stored_credentials)
    
    async def _authenticate_with_stored_credentials(self, stored_credentials) -> Union[NextStep, Authentication]:

        self._user_info_cache.from_dict(stored_credentials)
        if (self._user_info_cache.is_initialized()):
            await self._websocket_client.communication_queues["websocket"].put({'mode': AuthCall.TOKEN})
            result = await self._get_websocket_auth_step()
            if (result != UserActionRequired.NoActionRequired):
                logger.info("Unexpected Action Required after token login. " + str(result) + ". Can be caused when credentials expire or are deactivated. Falling back to normal login")
                self._user_info_cache.Clear()
                return next_step_response_simple(DisplayUriHelper.LOGIN)
            else:
                return Authentication(self._user_info_cache.steam_id, self._user_info_cache.persona_name)
        else:
            logger.warning("User Info Cache not initialized properly. Falling back to normal login.")
            return next_step_response_simple(DisplayUriHelper.LOGIN)

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
