import asyncio
import logging
import platform
import subprocess
import ssl
import sys
import webbrowser
import time
from functools import partial
from contextlib import suppress
from typing import List, Optional, NewType, Dict, AsyncGenerator, Any, Callable, Type

import traceback

import certifi
from galaxy.api.plugin import Plugin, create_and_run_plugin
from galaxy.api.types import (
    LocalGame,
    LocalGameState,
    UserPresence,
    UserInfo,
    Game,
    GameLibrarySettings,
    GameTime,
    Achievement,
    SubscriptionGame,
    Subscription,
)
from galaxy.api.errors import (
    AccessDenied,
    InvalidCredentials,
    NetworkError,
    UnknownError,
)
from galaxy.api.consts import Platform

from backend_interface import BackendInterface
from backend_steam_network import SteamNetworkBackend
from http_client import HttpClient
from client import (
    StateFlags,
    local_games_list,
    get_state_changes,
    get_client_executable,
    load_vdf,
    get_library_folders,
    get_app_manifests,
    app_id_from_manifest_path,
)
from persistent_cache_state import PersistentCacheState
from registry_monitor import get_steam_registry_monitor
from uri_scheme_handler import is_uri_handler_installed
from version import __version__


logger = logging.getLogger(__name__)

Timestamp = NewType("Timestamp", int)

COOLDOWN_TIME = 5
AUTH_SETUP_ON_VERSION__CACHE_KEY = "auth_setup_on_version"


def is_windows():
    return platform.system().lower() == "windows"


class SteamPlugin(Plugin):
    def __init__(self, reader, writer, token):
        super().__init__(Platform.Steam, __version__, reader, writer, token)

        # local features
        self._regmon = get_steam_registry_monitor()
        self._local_games_cache: Optional[List[LocalGame]] = None
        self._last_launch: Timestamp = 0
        self._update_local_games_task = asyncio.create_task(asyncio.sleep(0))

        # http client
        self._ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self._ssl_context.load_verify_locations(certifi.where())
        self._http_client = HttpClient()

        # cache management
        self._persistent_storage_state = PersistentCacheState()
        self._pushing_cache_task = asyncio.create_task(asyncio.sleep(0))

        # backend client
        self.__backend: Optional[BackendInterface] = None
        self.__backend_mode : Type[BackendInterface] = SteamNetworkBackend

    @property
    def features(self):
        non_backend_features = set(super().features) - set(BackendInterface.POSSIBLE_FEATURES)
        return list(non_backend_features | self.__backend_mode.features())

    @property
    def _backend(self) -> BackendInterface:
        if self.__backend is None:
            raise UnknownError("Backend not set")
        return self.__backend
    
    def handshake_complete(self):
        self.__backend = self._load_steam_network_backend()
        logger.info("Handshake complete")

    def _load_steam_network_backend(self):
        http_client : HttpClient = self._http_client
        persistent_storage_state=self._persistent_storage_state
        persistent_cache=self.persistent_cache
        store_credentials=self.store_credentials
        ssl_context=self._ssl_context
        update_user_presence=self.update_user_presence
        add_game=self.add_game

        return SteamNetworkBackend(http_client, ssl_context, persistent_storage_state, persistent_cache, update_user_presence, store_credentials, add_game)
    
    async def pass_login_credentials(self, step, credentials, cookies):
        result = await self._backend.pass_login_credentials(step, credentials, cookies)
        self.__store_current_version_in_cache(key=AUTH_SETUP_ON_VERSION__CACHE_KEY)
        return result

    def __store_current_version_in_cache(self, key: str):
        if self.persistent_cache.get(key) != __version__:
            self.persistent_cache[key] = __version__
            self.push_cache()
        
    async def authenticate(self, stored_credentials=None):
        try:
            auth = await self._backend.authenticate(stored_credentials)
        except NetworkError:  # casuses "Offline. Retry"
            raise
        except (
            InvalidCredentials, AccessDenied,  # re-raised would cause "Connection Lost"
            Exception  # re-raised would cause "Offline. Retry"
        ) as e:
            logger.error(traceback.format_exc())
            logger.warning(f"Authentication for initial backend failed with {e!r}")
            raise e

        return auth

    async def shutdown(self):
        self._regmon.close()
        await self._http_client.close()
        await self._backend.shutdown()

        with suppress(asyncio.CancelledError):
            self._update_local_games_task.cancel()
            self._pushing_cache_task.cancel()
            await self._update_local_games_task
            await self._pushing_cache_task

    async def get_owned_games(self) -> List[Game]:
        return await self._backend.get_owned_games()

    async def get_subscriptions(self) -> List[Subscription]:
        return await self._backend.get_subscriptions()

    async def prepare_subscription_games_context(self, subscription_names: List[str]) -> Any:
        return await self._backend.prepare_subscription_games_context(subscription_names)

    async def get_subscription_games(
        self, subscription_name: str, context: Any
    ) -> AsyncGenerator[List[SubscriptionGame], None]:
        async for hunk in self._backend.get_subscription_games(subscription_name, context):
            yield hunk

    async def prepare_achievements_context(self, game_ids: List[str]) -> Any:
        return await self._backend.prepare_achievements_context(game_ids)

    async def get_unlocked_achievements(self, game_id: str, context: Any) -> List[Achievement]:
        return await self._backend.get_unlocked_achievements(game_id, context)

    async def prepare_game_times_context(self, game_ids: List[str]) -> Any:
        return await self._backend.prepare_game_times_context(game_ids)

    async def get_game_time(self, game_id: str, context: Dict[int, int]) -> GameTime:
        return await self._backend.get_game_time(game_id, context)

    async def prepare_game_library_settings_context(self, game_ids: List[str]) -> Any:
        return await self._backend.prepare_game_library_settings_context(game_ids)

    async def get_game_library_settings(self, game_id: str, context: Any) -> GameLibrarySettings:
        return await self._backend.get_game_library_settings(game_id, context)

    async def get_friends(self) -> List[UserInfo]:
        return await self._backend.get_friends()

    async def prepare_user_presence_context(self, user_ids: List[str]) -> Any:
        return await self._backend.prepare_user_presence_context(user_ids)

    async def get_user_presence(self, user_id: str, context: Any) -> UserPresence:
        return await self._backend.get_user_presence(user_id, context)

    def achievements_import_complete(self):
        self._backend.achievements_import_complete()

    def game_times_import_complete(self):
        self._backend.game_times_import_complete()

    def game_library_settings_import_complete(self):
        self._backend.game_library_settings_import_complete()

    def user_presence_import_complete(self):
        self._backend.user_presence_import_complete()

    def subscription_games_import_complete(self):
        self._backend.subscription_games_import_complete()

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

    async def _push_cache(self):
        self.push_cache()
        self._persistent_storage_state.modified = False
        await asyncio.sleep(
            COOLDOWN_TIME
        )  # lower pushing cache rate to do not clog socket in case of big cache

    def tick(self):
        self._backend.tick()

        if (
            self._local_games_cache is not None
            and self._update_local_games_task.done()
            and self._regmon.is_updated()
        ):
            self._update_local_games_task = asyncio.create_task(self._update_local_games())

        if self._pushing_cache_task.done() and self._persistent_storage_state.modified:
            self._pushing_cache = asyncio.create_task(self._push_cache())

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

    async def prepare_local_size_context(self, game_ids: List[str]) -> Dict[str, str]:
        library_folders = get_library_folders()
        app_manifests = list(get_app_manifests(library_folders))
        return {app_id_from_manifest_path(path): path for path in app_manifests}

    async def get_local_size(self, game_id: str, context: Dict[str, str]) -> Optional[int]:
        try:
            manifest_path = context[game_id]
        except KeyError:  # not installed
            return 0
        try:
            manifest = load_vdf(manifest_path)
            app_state = manifest["AppState"]
            state_flags = StateFlags(int(app_state["StateFlags"]))
            if StateFlags.FullyInstalled in state_flags:
                return int(app_state["SizeOnDisk"])
            else:  # as SizeOnDisk is 0
                return int(app_state["BytesDownloaded"])
        except Exception as e:
            logger.warning("Cannot parse SizeOnDisk in %s: %r", manifest_path, e)
            return None

    async def shutdown_platform_client(self) -> None:
        launch_debounce_time = 30
        if time.time() < self._last_launch + launch_debounce_time:
            # workaround for quickly closed game (Steam sometimes dumps false positive just after a launch)
            logging.info("Ignoring shutdown request because game was launched a moment ago")
            return
        if is_windows():
            exe = get_client_executable()
            if exe is None:
                return
            cmd = '"{}" -shutdown -silent'.format(exe)
        else:
            cmd = "osascript -e 'quit app \"Steam\"'"
        logger.debug("Running command '%s'", cmd)
        process = await asyncio.create_subprocess_shell(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        await process.communicate()


def main():
    create_and_run_plugin(SteamPlugin, sys.argv)


if __name__ == "__main__":
    main()
