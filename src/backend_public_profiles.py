import asyncio
import contextlib
import webbrowser
import json
import logging
from typing import Any, Dict, List, Callable, Type
from urllib import parse

from galaxy.api.consts import LicenseType
from galaxy.api.errors import (
    AccessDenied, AuthenticationRequired, UnknownBackendResponse, UnknownError, InvalidCredentials
)
from galaxy.api.jsonrpc import InvalidParams
from galaxy.api.types import (
    Achievement, Authentication, Game, GameTime, LicenseInfo, GameLibrarySettings
)

import achievements_cache
from backend_interface import BackendInterface
from cache import Cache
from http_client import HttpClient
from leveldb_parser import LevelDbParser
from persistent_cache_state import PersistentCacheState
from public_profiles.authentication import next_step_response, StartUri
from public_profiles.steamcommunity_scrapper import SteamHttpClient
from user_profile import UserProfileChecker, ProfileDoesNotExist, ProfileIsNotPublic, ParseError, \
    NotPublicGameDetailsOrUserHasNoGames

logger = logging.getLogger(__name__)


GAME_DOES_NOT_SUPPORT_LAST_PLAYED_VALUE = 86400


class PublicProfilesBackend(BackendInterface):
    def __init__(
        self,
        *,
        http_client: HttpClient,
        user_profile_checker: UserProfileChecker,
        persistent_storage_state: PersistentCacheState,
        persistent_cache: Dict[str, Any],
        store_credentials: Callable,
    ) -> None:

        self._steam_id = None
        self._miniprofile_id = None
        self._level_db_parser = None

        self._persistent_cache = persistent_cache
        self._persistent_storage_state = persistent_storage_state
        self._store_credentials = store_credentials

        self._client = SteamHttpClient(http_client)
        self._user_profile_checker = user_profile_checker

        self._achievements_cache = Cache()
        self._achievements_cache_updated = False
        self._achievements_semaphore = asyncio.Semaphore(2)

        self._authentication_lost = lambda: None

        self._load_cache()
    
    def register_auth_lost_callback(self, callback: Callable):
        self._authentication_lost = callback

    def _load_cache(self):
        achievements_cache_ = self._persistent_cache.get("achievements")
        if achievements_cache_ is not None:
            try:
                achievements_cache_ = json.loads(achievements_cache_)
                self._achievements_cache = achievements_cache.from_dict(achievements_cache_)
            except Exception:
                logger.exception("Cannot deserialize achievements cache")
    
    @staticmethod
    def _decorate_name_with_public_profiles_indicator(name: str) -> str:
        return name + " (public)"

    async def _do_auth(self, steam_id):
        url = "https://steamcommunity.com/profiles/{}".format(steam_id)
        self._steam_id = steam_id
        self._miniprofile_id, persona_name = await self._client.get_profile_data(url)

        return Authentication(
            self._steam_id, 
            self._decorate_name_with_public_profiles_indicator(persona_name)
        )

    async def authenticate(self, stored_credentials=None):
        if not stored_credentials:
            return next_step_response(StartUri.LOGIN)
        steam_id = stored_credentials.get("steam_id")
        if not steam_id:
            raise InvalidCredentials("No Steam ID in stored credentials")

        # TODO translate credentials coming from SteamNetwork backend
        if not steam_id.isdigit():
            import base64
            steam_id = base64.b64decode(steam_id).decode('utf-8')
        
        try:
            await self._user_profile_checker.check_is_public_by_steam_id(steam_id)
        except (ProfileIsNotPublic, ProfileDoesNotExist, NotPublicGameDetailsOrUserHasNoGames):
            raise AccessDenied()
        except ParseError:
            raise UnknownBackendResponse()

        return await self._do_auth(steam_id)

    async def pass_login_credentials(self, step, credentials, cookies):
        try:
            end_uri = credentials['end_uri']
            parsed_url = parse.urlsplit(end_uri)
            params = parse.parse_qs(parsed_url.query)
            logger.info('params: %s' % params)
        except (KeyError, ValueError):
            raise InvalidParams()
        
        if "open_in_default_browser" in end_uri:
            webbrowser.open(params["link"][0])
            return next_step_response(StartUri.LOGIN)

        try:
            steam_id = params['steam_id'][0]
            await self._user_profile_checker.check_is_public_by_steam_id(steam_id)
        except (ProfileIsNotPublic, NotPublicGameDetailsOrUserHasNoGames):
            return next_step_response(StartUri.PROFILE_IS_NOT_PUBLIC)
        except ProfileDoesNotExist:
            return next_step_response(StartUri.PROFILE_DOES_NOT_EXIST)
        except ParseError:
            raise UnknownBackendResponse()
        except Exception as e:
            logger.warning(repr(e))
            return next_step_response(StartUri.LOGIN_FAILED)

        self._store_credentials({'steam_id': steam_id})
        auth = await self._do_auth(steam_id)
        return auth

    @contextlib.asynccontextmanager
    async def _handle_non_public_profile(self, error: Type[Exception]):
        try:
            yield
        except error:
            try:
                await self._user_profile_checker.check_is_public_by_steam_id(self._steam_id)
            except (ProfileIsNotPublic, ProfileDoesNotExist, NotPublicGameDetailsOrUserHasNoGames) as e:
                self._authentication_lost()
                raise AccessDenied(f"Profile not publicly reachable: {e}")
            except ParseError:
                raise UnknownBackendResponse()
            raise

    async def get_owned_games(self):
        if self._steam_id is None:
            raise AuthenticationRequired()

        async with self._handle_non_public_profile(UnknownBackendResponse):
            games = await self._client.get_games(self._steam_id)

        try:
            return [
                Game(str(game["appid"]), game["name"], [], LicenseInfo(LicenseType.SinglePurchase, None))
                for game in games
            ]
        except (KeyError, ValueError):
            logger.exception("Cannot parse backend response: %s", games)
            raise UnknownBackendResponse()

    async def prepare_achievements_context(self, game_ids: List[str]) -> Any:
        if self._steam_id is None:
            raise AuthenticationRequired()

        return await self._get_game_achivement_info_dict()

    async def get_unlocked_achievements(self, game_id: str, context: Any) -> List[Achievement]:
        achivement_info = context.get(game_id)
        if achivement_info is None:
            logger.error("Game {} not owned".format(game_id))
            raise UnknownError("Game {} not owned".format(game_id))

        if not achivement_info["stats_url"]:
            return []

        fingerprint = achievements_cache.Fingerprint(None, achivement_info["time_played"])
        achievements = self._achievements_cache.get(game_id, fingerprint)

        if achievements is not None:
           # return from cache
           return achievements

        # fetch from http_client and update cache
        achievements = await self._get_achievements(achivement_info["stats_url"])
        self._achievements_cache.update(game_id, achievements, fingerprint)
        self._achievements_cache_updated = True
        return achievements

    def achievements_import_complete(self) -> None:
        if self._achievements_cache_updated:
            self._persistent_cache["achievements"] = achievements_cache.as_dict(self._achievements_cache)
            self._persistent_storage_state.modified = True
            self._achievements_cache_updated = False

    async def _get_achievements(self, stats_url):
        async with self._achievements_semaphore:
            achievements = await self._client.get_achievements(stats_url)
            return [Achievement(unlock_time, None, name) for unlock_time, name in achievements]

    async def _get_game_achivement_info_dict(self) -> Dict[str, GameTime]:
        games = await self._client.get_games(self._steam_id)

        game_achivement_infos = {}

        try:
            for game in games:
                game_achivement_infos[str(game["appid"])] = {
                    "stats_url": game["statsLink"],
                    "time_played": int(float((game["hoursOnRecord"] or "0").replace(",", "")) * 60),
                }
        except (KeyError, ValueError):
            logger.exception("Cannot parse backend response")
            raise UnknownBackendResponse()

        return game_achivement_infos

    async def prepare_game_times_context(self, game_ids: List[str]) -> Any:
        if self._steam_id is None:
            raise AuthenticationRequired()

        return await self._get_game_times_dict()

    async def get_game_time(self, game_id: str, context: Any) -> GameTime:
        game_time = context.get(game_id)
        if game_time is None:
            raise UnknownError("Game {} not owned".format(game_id))
        return game_time

    async def _get_game_times_dict(self) -> Dict[str, GameTime]:
        games = await self._client.get_games(self._steam_id)

        game_times = {}

        try:
            for game in games:
                game_id = str(game["appid"])
                # last_played = game.get("last_played")
                # if last_played == GAME_DOES_NOT_SUPPORT_LAST_PLAYED_VALUE:
                #     last_played = None
                last_played = None
                game_times[game_id] = GameTime(
                    game_id,
                    int(float((game["hoursOnRecord"] or "0").replace(",", "")) * 60),
                    last_played
                )
        except (KeyError, ValueError):
            logger.exception("Cannot parse backend response")
            raise UnknownBackendResponse()

        return game_times

    async def prepare_game_library_settings_context(self, game_ids: List[str]) -> Any:
        if self._steam_id is None:
            raise AuthenticationRequired()

        if not self._level_db_parser:
            self._level_db_parser = LevelDbParser(self._miniprofile_id)

        self._level_db_parser.parse_leveldb()

        if not self._level_db_parser.lvl_db_is_present:
            return None
        else:
            leveldb_static_games_collections_dict = self._level_db_parser.get_static_collections_tags()
            logger.info(f"Leveldb static settings dict {leveldb_static_games_collections_dict}")
            return leveldb_static_games_collections_dict

    async def get_game_library_settings(self, game_id: str, context: Any) -> GameLibrarySettings:
        if not context:
            return GameLibrarySettings(game_id, None, None)
        else:
            game_tags = context.get(game_id)
            if not game_tags:
                return GameLibrarySettings(game_id, [], False)

            hidden = False
            for tag in game_tags:
                if tag.lower() == 'hidden':
                    hidden = True
            if hidden:
                game_tags.remove('hidden')
            return GameLibrarySettings(game_id, game_tags, hidden)

    async def get_friends(self):
        if self._steam_id is None:
            raise AuthenticationRequired()

        return await self._client.get_friends(self._steam_id)
