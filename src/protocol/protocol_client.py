import asyncio
import logging
import enum
import galaxy.api.errors

from protocol.protobuf_client import ProtobufClient, SteamLicense
from protocol.consts import EResult, EFriendRelationship, EPersonaState, STEAM_CLIENT_APP_ID
from friends_cache import FriendsCache
from games_cache import GamesCache
from stats_cache import StatsCache
from user_info_cache import UserInfoCache
from times_cache import TimesCache
from ownership_ticket_cache import OwnershipTicketCache

from typing import List


logger = logging.getLogger(__name__)

def translate_error(result: EResult):
    assert result != EResult.OK
    data = {
        "result": result
    }
    if result in (
        EResult.InvalidPassword,
        EResult.AccountNotFound,
        EResult.InvalidSteamID,
        EResult.InvalidLoginAuthCode,
        EResult.AccountLogonDeniedNoMailSent,
        EResult.AccountLoginDeniedNeedTwoFactor,
        EResult.TwoFactorCodeMismatch,
        EResult.TwoFactorActivationCodeMismatch
    ):
        return galaxy.api.errors.InvalidCredentials(data)
    if result in (
        EResult.ConnectFailed,
        EResult.IOFailure,
        EResult.RemoteDisconnect
    ):
        return galaxy.api.errors.NetworkError(data)
    if result in (
        EResult.Busy,
        EResult.ServiceUnavailable,
        EResult.Pending,
        EResult.IPNotFound,
        EResult.TryAnotherCM,
        EResult.Cancelled
    ):
        return galaxy.api.errors.BackendNotAvailable(data)
    if result == EResult.Timeout:
        return galaxy.api.errors.BackendTimeout(data)
    if result in (
        EResult.RateLimitExceeded,
        EResult.LimitExceeded,
        EResult.Suspended,
        EResult.AccountLocked,
        EResult.AccountLogonDeniedVerifiedEmailRequired
    ):
        return galaxy.api.errors.TemporaryBlocked(data)
    if result == EResult.Banned:
        return galaxy.api.errors.Banned(data)
    if result in (
        EResult.AccessDenied,
        EResult.InsufficientPrivilege,
        EResult.LogonSessionReplaced,
        EResult.Blocked,
        EResult.Ignored,
        EResult.AccountDisabled,
        EResult.AccountNotFeatured
    ):
        return galaxy.api.errors.AccessDenied(data)
    if result in (
        EResult.DataCorruption,
        EResult.DiskFull,
        EResult.RemoteCallFailed,
        EResult.RemoteFileConflict,
        EResult.BadResponse
    ):
        return galaxy.api.errors.BackendError(data)

    return galaxy.api.errors.UnknownError(data)


class UserActionRequired(enum.IntEnum):
    NoActionRequired = 0
    EmailTwoFactorInputRequired = 1
    PhoneTwoFactorInputRequired = 2
    PasswordRequired = 3
    InvalidAuthData = 4


class ProtocolClient:
    _STATUS_FLAG = 1106

    def __init__(self,
        socket,
        friends_cache: FriendsCache,
        games_cache: GamesCache,
        translations_cache: dict,
        stats_cache: StatsCache,
        times_cache: TimesCache,
        user_info_cache: UserInfoCache,
        ownership_ticket_cache: OwnershipTicketCache,
        used_server_cell_id,
    ):

        self._protobuf_client = ProtobufClient(socket)
        self._protobuf_client.log_on_handler = self._log_on_handler
        self._protobuf_client.log_off_handler = self._log_off_handler
        self._protobuf_client.relationship_handler = self._relationship_handler
        self._protobuf_client.user_info_handler = self._user_info_handler
        self._protobuf_client.user_nicknames_handler = self._user_nicknames_handler
        self._protobuf_client.app_info_handler = self._app_info_handler
        self._protobuf_client.package_info_handler = self._package_info_handler
        self._protobuf_client.app_ownership_ticket_handler = self._app_ownership_ticket_handler
        self._protobuf_client.license_import_handler = self._license_import_handler
        self._protobuf_client.translations_handler = self._translations_handler
        self._protobuf_client.stats_handler = self._stats_handler
        self._protobuf_client.times_handler = self._times_handler
        self._protobuf_client.user_authentication_handler = self._user_authentication_handler
        self._protobuf_client.sentry = self._get_sentry
        self._protobuf_client.times_import_finished_handler = self._times_import_finished_handler
        self._friends_cache = friends_cache
        self._games_cache = games_cache
        self._translations_cache = translations_cache
        self._stats_cache = stats_cache
        self._user_info_cache = user_info_cache
        self._times_cache = times_cache
        self._ownership_ticket_cache = ownership_ticket_cache
        self._auth_lost_handler = None
        self._login_future = None
        self._used_server_cell_id = used_server_cell_id

    async def close(self, is_socket_connected):
        await self._protobuf_client.close(is_socket_connected)

    async def wait_closed(self):
        await self._protobuf_client.wait_closed()

    async def run(self):
        await self._protobuf_client.run()

    async def get_steam_app_ownership_ticket(self):
        await self._protobuf_client.get_app_ownership_ticket(STEAM_CLIENT_APP_ID)

    async def register_auth_ticket_with_cm(self, ticket: bytes):
        await self._protobuf_client.register_auth_ticket_with_cm(ticket)

    async def authenticate_password(self, account_name, password, two_factor, two_factor_type, auth_lost_handler):
        loop = asyncio.get_running_loop()
        self._login_future = loop.create_future()
        await self._protobuf_client.log_on_password(account_name, password, two_factor, two_factor_type)
        result = await self._login_future
        logger.info(result)
        if result == EResult.OK:
            self._auth_lost_handler = auth_lost_handler
        elif result == EResult.AccountLogonDenied:
            self._auth_lost_handler = auth_lost_handler
            return UserActionRequired.EmailTwoFactorInputRequired
        elif result == EResult.AccountLoginDeniedNeedTwoFactor:
            self._auth_lost_handler = auth_lost_handler
            return UserActionRequired.PhoneTwoFactorInputRequired
        elif result in (EResult.InvalidPassword,
                        EResult.InvalidSteamID,
                        EResult.AccountNotFound,
                        EResult.InvalidLoginAuthCode,
                        EResult.TwoFactorCodeMismatch,
                        EResult.TwoFactorActivationCodeMismatch
                        ):
            self._auth_lost_handler = auth_lost_handler
            return UserActionRequired.InvalidAuthData
        else:
            logger.warning(f"Received unknown error, code: {result}")
            raise translate_error(result)

        await self._protobuf_client.account_info_retrieved.wait()
        await self._protobuf_client.login_key_retrieved.wait()
        return UserActionRequired.NoActionRequired

    async def authenticate_token(self, steam_id, account_name, token, auth_lost_handler):
        loop = asyncio.get_running_loop()
        self._login_future = loop.create_future()
        await self._protobuf_client.log_on_token(steam_id, account_name, token, self._used_server_cell_id)
        result = await self._login_future
        if result == EResult.OK:
            self._auth_lost_handler = auth_lost_handler
        elif result == EResult.InvalidPassword:
            raise galaxy.api.errors.InvalidCredentials({"result": result})
        else:
            logger.warning(f"Received unknown error, code: {result}")
            raise translate_error(result)

        await self._protobuf_client.account_info_retrieved.wait()
        return UserActionRequired.NoActionRequired

    async def import_game_stats(self, game_ids):
        for game_id in game_ids:
            self._protobuf_client.job_list.append({"job_name": "import_game_stats",
                                                   "game_id": game_id})

    async def import_game_times(self):
        self._protobuf_client.job_list.append({"job_name": "import_game_times"})

    async def retrieve_collections(self):
        self._protobuf_client.job_list.append({"job_name": "import_collections"})
        await self._protobuf_client.collections['event'].wait()
        collections = self._protobuf_client.collections['collections'].copy()
        self._protobuf_client.collections['event'].clear()
        self._protobuf_client.collections['collections'] = dict()
        return collections

    async def _log_on_handler(self, result: EResult):
        assert self._login_future is not None
        self._login_future.set_result(result)

    async def _log_off_handler(self, result):
        logger.warning("Logged off, result: %d", result)
        if self._auth_lost_handler is not None:
            await self._auth_lost_handler(translate_error(result))

    async def _relationship_handler(self, incremental, friends):
        logger.info(f"Received relationships: incremental={incremental}, friends={friends}")
        initial_friends = []
        new_friends = []
        for user_id, relationship in friends.items():
            if relationship == EFriendRelationship.Friend:
                if incremental:
                    self._friends_cache.add(user_id)
                    new_friends.append(user_id)
                else:
                    initial_friends.append(user_id)
            elif relationship == EFriendRelationship.None_:
                assert incremental
                self._friends_cache.remove(user_id)

        if not incremental:
            self._friends_cache.reset(initial_friends)
            # set online state to get friends statuses
            await self._protobuf_client.set_persona_state(EPersonaState.Invisible)
            await self._protobuf_client.get_friends_statuses()
            await self._protobuf_client.get_user_infos(initial_friends, self._STATUS_FLAG)

        if new_friends:
            await self._protobuf_client.get_friends_statuses()
            await self._protobuf_client.get_user_infos(new_friends, self._STATUS_FLAG)

    async def _user_info_handler(self, user_id, user_info):
        logger.info(f"Received user info: user_id={user_id}, user_info={user_info}")
        await self._friends_cache.update(user_id, user_info)

    async def _user_nicknames_handler(self, nicknames):
        logger.info(f"Received user nicknames {nicknames}")
        self._friends_cache.update_nicknames(nicknames)

    async def _license_import_handler(self, steam_licenses: List[SteamLicense]):
        logger.info('Handling %d user licenses', len(steam_licenses))
        not_resolved_licenses = []

        resolved_packages = self._games_cache.get_resolved_packages()
        package_ids = set([str(steam_license.license.package_id) for steam_license in steam_licenses])

        for steam_license in steam_licenses:
            if str(steam_license.license.package_id) not in resolved_packages:
                not_resolved_licenses.append(steam_license)

        if len(package_ids) < 12000:
            # TODO rework cache invalidation for bigger libraries (steam sends licenses in packs of >12k licenses)
            if package_ids != self._games_cache.get_package_ids():
                logger.info(
                    "Licenses list different than last time (cached packages: %d, new packages: %d). Reseting cache.",
                    len(self._games_cache.get_package_ids()),
                    len(package_ids)
                )
                self._games_cache.reset_storing_map()
                self._games_cache.start_packages_import(steam_licenses)
                return await self._protobuf_client.get_packages_info(steam_licenses)

        # This path will only attempt import on packages which aren't resolved (dont have any apps assigned)
        logger.info("Starting license import for %d packages, skipping %d already resolved.",
            len(package_ids - resolved_packages),
            len(resolved_packages)
        )
        self._games_cache.start_packages_import(not_resolved_licenses)
        await self._protobuf_client.get_packages_info(not_resolved_licenses)

    def _app_info_handler(self, appid, package_id=None, title=None, type=None, parent=None):
        if package_id:
            self._games_cache.update_license_apps(package_id, appid)
        if title and type:
            self._games_cache.update_app_title(appid, title, type, parent)

    def _package_info_handler(self):
        self._games_cache.update_packages()

    async def _app_ownership_ticket_handler(self, appid: int, ticket: bytes):
        if appid == STEAM_CLIENT_APP_ID:
            logger.info('Storing steam app ownership ticket')
            self._ownership_ticket_cache.ticket = ticket
        else:
            logger.debug(f'Ignoring app_id {appid} in ownership ticket handler')

    async def _translations_handler(self, appid, translations=None):
        if appid and translations:
            self._translations_cache[appid] = translations[0]
        elif appid not in self._translations_cache:
            self._translations_cache[appid] = None
            await self._protobuf_client.get_presence_localization(appid)

    async def _stats_handler(self, game_id, stats, achievements):
        self._stats_cache.update_stats(str(game_id), stats, achievements)

    async def _user_authentication_handler(self, key, value):
        logger.info(f"Updating user info cache with new {key}")
        if key == 'token':
            self._user_info_cache.token = value
        if key == 'steam_id':
            self._user_info_cache.steam_id = value
        if key == 'account_id':
            self._user_info_cache.account_id = value
        if key == 'account_username':
            self._user_info_cache.account_username = value
        if key == 'persona_name':
            self._user_info_cache.persona_name = value
        if key == 'two_step':
            self._user_info_cache.two_step = value
        if key == 'sentry':
            self._user_info_cache.sentry = value

    async def _get_sentry(self):
        return self._user_info_cache.sentry

    async def _times_handler(self, game_id, time_played, last_played):
        self._times_cache.update_time(str(game_id), time_played, last_played)

    async def _times_import_finished_handler(self, finished):
        self._times_cache.times_import_finished(finished)
