import os
import platform
from textwrap import dedent

import pytest
from galaxy.api.types import LocalGame, LocalGameState

from client import (
    get_app_states_from_registry, get_custom_library_folders, get_library_folders, local_games_list
 )


@pytest.fixture()
def mock_get_library_folders(mocker):
    return mocker.patch("client.get_library_folders")


@pytest.fixture()
def mock_get_installed_games(mocker):
    return mocker.patch("client.get_installed_games")


@pytest.fixture()
def mock_get_app_states_from_registry(mocker):
    mocker.patch("client.registry_apps_as_dict")
    return mocker.patch("client.get_app_states_from_registry")


def test_dict_to_list_empty():
    assert get_app_states_from_registry({}) == {}


def test_dict_to_list_no_fields():
    input = {
        "1234": {
        }
    }
    assert get_app_states_from_registry(input) == {
        "1234": LocalGameState.None_
    }


def test_dict_to_list_no_none():
    input = {
        "1234": {
            "running": 0,
            "installed": 0,
        }
    }
    assert get_app_states_from_registry(input) == {
        "1234": LocalGameState.None_
    }


def test_dict_to_list_installed():
    input = {
        "1234": {
            "running": 0,
            "inStaLleD": 1,
        }
    }
    assert get_app_states_from_registry(input) == {
        "1234": LocalGameState.Installed
    }


def test_dict_to_list_running():
    input = {
        "1234": {
            "running": 1,
            "inStaLleD": 0,
        }
    }
    assert get_app_states_from_registry(input) == {
        "1234": LocalGameState.Running
    }


def test_dict_to_list_installed_and_running():
    input = {
        "1234": {
            "Running": 1,
            "inStaLleD": 1,
        }
    }
    assert get_app_states_from_registry(input) == {
        "1234": LocalGameState.Installed | LocalGameState.Running
    }


def test_values_as_string():
    input = {
        "1234": {
            "running": "1",
            "installed": "1",
        }
    }
    assert get_app_states_from_registry(input) == {
        "1234": LocalGameState.Installed | LocalGameState.Running
    }


def test_get_app_id_success(tmp_path):
    data = """\
        "漢字не_аски"
        {
        }
        "AppState"
        {
            "appid"		"92700"
            "Universe"		"1"
            "name"		"Shadow Harvest: Phantom Ops"
            "StateFlags"		"4"
            "installdir"		"Shadow Harvest"
            "LastUpdated"		"1505203687"
            "UpdateResult"		"0"
            "SizeOnDisk"		"4281183222"
            "buildid"		"25489"
            "LastOwner"		"399493"
            "BytesToDownload"		"0"
            "BytesDownloaded"		"0"
            "AutoUpdateBehavior"		"0"
            "AllowOtherDownloadsWhileRunning"		"0"
            "UserConfig"
            {
                "language"		"english"
            }
            "InstalledDepots"
            {
                "92702"
                {
                    "manifest"		"8335697587195428853"
                }
                "92703"
                {
                    "manifest"		"8659569355878638955"
                }
                "92705"
                {
                    "manifest"		"4222837831210184821"
                }
                "92707"
                {
                    "manifest"		"6694277017015437096"
                }
                "92706"
                {
                    "manifest"		"1564469745251743738"
                }
                "92704"
                {
                    "manifest"		"2386227316175199586"
                }
                "92701"
                {
                    "manifest"		"5802359068436116460"
                }
                "92708"
                {
                    "manifest"		"7888111964541370664"
                }
            }
            "MountedDepots"
            {
                "92702"		"8335697587195428853"
                "92703"		"8659569355878638955"
                "92705"		"4222837831210184821"
                "92707"		"6694277017015437096"
                "92706"		"1564469745251743738"
                "92704"		"2386227316175199586"
                "92701"		"5802359068436116460"
                "92708"		"7888111964541370664"
            }
        }
    """
    path = tmp_path / "appmanifest_92700.acf"
    path.write_text(dedent(data), encoding="utf-8")
    assert os.path.basename(path)[12:-4] == "92700"


def test_get_custom_library_folders_old_format(tmp_path):
    data = """\
        "LibraryFolders"
        {
            "TimeNextStatsReport"		"1507807583"
            "ContentStatsID"		"313251607278753000"
            "1"		"D:\\Steam"
            "2"		"E:\\Games\\Steam"
        }
    """
    path = tmp_path / "libraryfolders.vdf"
    path.write_text(dedent(data))
    library_folders = get_custom_library_folders(path)
    assert library_folders == [
        os.path.join(r"D:\Steam", "steamapps"),
        os.path.join(r"E:\Games\Steam", "steamapps")
    ]


def test_get_custom_library_folders_new_format(tmp_path):
    data = """\
        "LibraryFolders"
        {
            "ContentStatsID"		"313251607278753000"
            "1"
            {
                "path"		"D:\\Steam"
                "label"		"Games"
                "mounted"		"1"
                "contentid"		"24707729912644713069"
            }
            "2"
            {
                "path"		"E:\\Games\\Steam"
                "label"		"Extras"
                "mounted"		"2"
                "contentid"		"24307526915614213469"
            }
        }
    """
    path = tmp_path / "libraryfolders.vdf"
    path.write_text(dedent(data))
    library_folders = get_custom_library_folders(path)
    assert library_folders == [
        os.path.join(r"D:\Steam", "steamapps"),
        os.path.join(r"E:\Games\Steam", "steamapps")
    ]


def test_get_custom_library_folders_empty(tmp_path):
    data = """\
        "LibraryFolders"
        {
            "TimeNextStatsReport"		"1507807583"
            "ContentStatsID"		"313251607278753000"
        }
    """
    path = tmp_path / "libraryfolders.vdf"
    path.write_text(dedent(data))
    library_folders = get_custom_library_folders(path)
    assert library_folders == []


@pytest.mark.parametrize(
    "data",
    [
        """\
            "LibraryFolders"
            {
        """,
        """\
            "ABC"
            {
            }
        """
    ],
    ids=[
        "invalid_vdf",
        "invalid_name"
    ]
)
def test_get_custom_library_folders_invalid_file(data, tmp_path):
    path = tmp_path / "libraryfolders.vdf"
    path.write_text(dedent(data))
    assert get_custom_library_folders(path) is None


def test_get_custom_library_folders_no_file(tmp_path):
    path = tmp_path / "libraryfolders.vdf"
    assert get_custom_library_folders(path) is None


@pytest.mark.skipif(platform.system() != "Windows", reason="Based on Windows registry")
def test_get_library_folders_no_steam(mocker):
    get_configuration_folder = mocker.patch("client.get_configuration_folder")
    get_configuration_folder.return_value = None
    assert get_library_folders() == []
    get_configuration_folder.assert_called_once_with()


def test_get_library_folders_parsing_error(mocker):
    path = "path"
    get_configuration_folder = mocker.patch("client.get_configuration_folder")
    get_configuration_folder.return_value = path
    get_custom_library_folders = mocker.patch("client.get_custom_library_folders")
    get_custom_library_folders.return_value = None
    assert get_library_folders() == [os.path.join(path, 'steamapps')]
    get_custom_library_folders.assert_called_once_with(os.path.join(path, "steamapps", "libraryfolders.vdf"))


def test_local_games_list_no_steam(mocker):
    get_library_folders = mocker.patch("client.get_library_folders")
    get_library_folders.return_value = []
    assert local_games_list() == []
    get_library_folders.assert_called_once_with()


def test_local_games_list_no_games(
    mock_get_library_folders,
    mock_get_installed_games,
    mock_get_app_states_from_registry
):
    library_folders = ["cofiguration_path"]
    mock_get_library_folders.return_value = library_folders
    mock_get_installed_games.return_value = []
    mock_get_app_states_from_registry.return_value = {}
    assert local_games_list() == []
    mock_get_library_folders.assert_called_once_with()
    mock_get_installed_games.assert_called_once_with(library_folders)
    mock_get_app_states_from_registry.assert_called_once()


def test_local_games_list_no_registry(
    mock_get_library_folders,
    mock_get_installed_games,
    mock_get_app_states_from_registry
):
    library_folders = ["cofiguration_path"]
    mock_get_library_folders.return_value = library_folders
    mock_get_installed_games.return_value = [
        "1513", "12351"
    ]
    mock_get_app_states_from_registry.return_value = {}
    assert local_games_list() == []


def test_local_games_list(
    mock_get_library_folders,
    mock_get_installed_games,
    mock_get_app_states_from_registry
):
    library_folders = ["cofiguration_path"]
    mock_get_library_folders.return_value = library_folders
    mock_get_installed_games.return_value = [
        "1513", "12351"
    ]
    mock_get_app_states_from_registry.return_value = {
        "1513": LocalGameState.Installed,
        "12351": LocalGameState.Installed | LocalGameState.Running,
        "89123": LocalGameState.Installed
    }
    assert local_games_list() == [
        LocalGame("1513", LocalGameState.Installed),
        LocalGame("12351", LocalGameState.Installed | LocalGameState.Running)
    ]


@pytest.mark.parametrize("data_file, game_id", [
    ("appmanifest_787480.acf", "787480"),
    ("appmanifest_970570.acf", "970570")
])
def test_get_app_id_real_data(data_file, game_id):
    real_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), data_file)
    assert os.path.exists(real_path)
    assert os.path.basename(real_path)[12:-4] == game_id
