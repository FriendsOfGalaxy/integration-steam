import glob
import itertools
import logging
import os
import enum
import platform
from typing import Iterable, List, Optional, Dict, Any

import vdf
from galaxy.api.types import LocalGame, LocalGameState


logger = logging.getLogger(__name__)


class StateFlags(enum.Flag):
    """StateFlags from appmanifest.acf file"""
    Invalid = 0
    Uninstalled = 1
    UpdateRequired = 2
    FullyInstalled = 4
    Encrypted = 8
    Locked = 16
    FilesMissing = 32
    AppRunning = 64
    FilesCorrupt = 128
    UpdateRunning = 256
    UpdatePaused = 512
    UpdateStarted = 1024
    Uninstalling = 2048
    BackupRunning = 4096
    Reconfiguring = 65536
    Validating = 131072
    AddingFiles = 262144
    Preallocating = 524288
    Downloading = 1048576
    Staging = 2097152
    Committing = 4194304
    UpdateStopping = 8388608


class CaseInsensitiveDict(dict):
    def __setitem__(self, key, value):
        super().__setitem__(key.lower(), value)

    def __getitem__(self, key):
        return super().__getitem__(key.lower())


def load_vdf(path: str) -> Dict[str, Any]:
    return vdf.load(open(path, encoding="utf-8", errors="replace"), mapper=CaseInsensitiveDict)


# Windows registry implementation
if platform.system() == "Windows":
    import winreg


    def registry_apps_as_dict():
        try:
            apps = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam\Apps")
        except OSError as e:
            logger.info("Steam Apps registry cannot be read: %s", str(e))
            return {}

        apps_dict = dict()
        sub_key_index = 0

        while True:
            try:
                sub_key_name = winreg.EnumKey(apps, sub_key_index)
            except OSError:
                # OSError marks end of the enumeration: https://docs.python.org/3/library/winreg.html#winreg.EnumKey
                break
            try:
                sub_key_dict = dict()
                with winreg.OpenKey(apps, sub_key_name) as sub_key:
                    value_index = 0
                    while True:
                        try:
                            v = winreg.EnumValue(sub_key, value_index)
                            sub_key_dict[v[0]] = v[1]
                            value_index += 1
                        except OSError:
                            break
                    winreg.CloseKey(sub_key)
                apps_dict[sub_key_name] = sub_key_dict
                sub_key_index += 1
            except OSError:
                logger.exception("Failed to parse Steam registry")
                break

        winreg.CloseKey(apps)

        return apps_dict


elif platform.system().lower() == "darwin":
    # MacOS "registry" implementation (registry.vdf file)
    def registry_apps_as_dict():
        try:
            registry = load_vdf(os.path.expanduser("~/Library/Application Support/Steam/registry.vdf"))
        except OSError:
            logger.exception("Failed to read Steam registry")
            return {}

        try:
            return registry["Registry"]["HKCU"]["Software"]["Valve"]["Steam"]["Apps"]
        except KeyError:
            logger.exception("Failed to parse Steam registry")
            return {}

# fallback for other systems
else:
    def registry_apps_as_dict():
        return {}


def get_app_states_from_registry(app_dict):
    app_states = {}
    for game, game_data in app_dict.items():
        state = LocalGameState.None_
        for k, v in game_data.items():
            if k.lower() == "running" and str(v) == "1":
                state |= LocalGameState.Running
            if k.lower() == "installed" and str(v) == "1":
                state |= LocalGameState.Installed
        app_states[game] = state

    return app_states


def local_games_list():
    local_games = []
    try:
        library_folders = get_library_folders()
        logger.debug("Checking library folders: %s", str(library_folders))
        apps_ids = get_installed_games(library_folders)
        app_states = get_app_states_from_registry(registry_apps_as_dict())
        for app_id in apps_ids:
            app_state = app_states.get(app_id)
            if app_state is None:
                continue
            local_game = LocalGame(app_id, app_state)
            local_games.append(local_game)
    except:
        logger.exception("Failed to get local games list")
    finally:
        return local_games


def get_state_changes(old_list, new_list):
    old_dict = {x.game_id: x.local_game_state for x in old_list}
    new_dict = {x.game_id: x.local_game_state for x in new_list}
    result = []
    # removed games
    result.extend(LocalGame(id, LocalGameState.None_) for id in old_dict.keys() - new_dict.keys())
    # added games
    result.extend(local_game for local_game in new_list if local_game.game_id in new_dict.keys() - old_dict.keys())
    # state changed
    result.extend(
        LocalGame(id, new_dict[id]) for id in new_dict.keys() & old_dict.keys() if new_dict[id] != old_dict[id])
    return result


def get_library_folders() -> Iterable[str]:
    configuration_folder = get_configuration_folder()
    if not configuration_folder:
        return []
    steam_apps_folder = os.path.join(configuration_folder, "steamapps")  # default location
    library_folders_config = os.path.join(steam_apps_folder, "libraryfolders.vdf")
    library_folders = get_custom_library_folders(library_folders_config) or []
    return [steam_apps_folder] + library_folders


def get_client_executable() -> Optional[str]:
    if platform.system() == "Windows":
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
            return str(winreg.QueryValueEx(key, "SteamExe")[0])
        except OSError:
            logger.info("Steam not installed")
            return None
    elif platform.system() == "Darwin":
        return "/Applications/Steam.app/Contents/MacOS/steam_osx"
    else:
        raise RuntimeError("Not supported OS")


def get_configuration_folder():
    if platform.system() == "Windows":
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
            return str(winreg.QueryValueEx(key, "SteamPath")[0])
        except OSError:
            logger.info("Steam not installed")
            return None
    elif platform.system().lower() == "darwin":
        return os.path.expanduser("~/Library/Application Support/Steam")
    else:
        raise RuntimeError("Not supported OS")


def get_custom_library_folders(config_path: str) -> Optional[List[str]]:
    """Parses library folders config file and returns a list of folders paths"""
    try:
        config = load_vdf(config_path)
        result = []
        for i in itertools.count(1):
            library_folders = config["LibraryFolders"]
            numerical_vdf_key = str(i)
            library_folder = library_folders.get(numerical_vdf_key)
            if library_folder is None:
                break
            if "path" in library_folder:
                library_path = library_folder.get("path")
            else:
                library_path = library_folder
            result.append(os.path.join(library_path, "steamapps"))
        return result
    except (OSError, SyntaxError, KeyError):
        logger.exception("Failed to parse %s", config_path)
        return None


def get_app_manifests(library_folders: Iterable[str]) -> Iterable[str]:
    for library_folder in library_folders:
        escaped_path = glob.escape(library_folder)
        yield from glob.iglob(os.path.join(escaped_path, "*.acf"))


def app_id_from_manifest_path(path):
    return os.path.basename(path)[len('appmanifest_'):-4]


def get_installed_games(library_paths: Iterable[str]) -> Iterable[str]:
    for app_manifest_path in get_app_manifests(library_paths):
        app_id = app_id_from_manifest_path(app_manifest_path)
        if app_id:
            yield app_id
