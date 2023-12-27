import pathlib
import pytest

from unittest.mock import MagicMock, PropertyMock, Mock, sentinel
from galaxy.unittest.mock import AsyncMock, async_return_value

from os import path
BASE_DIR = path.abspath(path.curdir)

import sys
sys.path.append(path.join(BASE_DIR, "src"))

from plugin import SteamPlugin, AUTH_SETUP_ON_VERSION__CACHE_KEY
from backend_interface import BackendInterface
from version import __version__


@pytest.fixture
def plugin_root_dir():
    import plugin as module
    return pathlib.Path(module.__file__).parent


@pytest.fixture()
def steam_id():
    return "123"


@pytest.fixture()
def login():
    return "tester"


@pytest.fixture()
def miniprofile():
    return 123


@pytest.fixture
def http_response_mock():
    mock = MagicMock(spec=(), name=http_response_mock.__name__)
    mock.text = AsyncMock()
    mock.json = AsyncMock()
    return mock


@pytest.fixture
def http_client_mock(http_response_mock):
    mock = MagicMock(spec=(), name=http_client_mock.__name__)
    mock.close = AsyncMock()
    mock.get = AsyncMock(return_value=http_response_mock)
    return mock


@pytest.fixture
def profile_checker():
    mock = MagicMock(spec=())
    mock.check_is_public_by_steam_id = AsyncMock()
    return mock


@pytest.fixture()
async def create_plugin(mocker, http_client_mock, profile_checker):
    created_plugins = []

    def function(cache=MagicMock()):
        writer = MagicMock(name="stream_writer")
        writer.drain.side_effect = lambda: async_return_value(None)

        mocker.patch('plugin.HttpClient', return_value=http_client_mock)
        mocker.patch("plugin.local_games_list", return_value=[])
        mocker.patch("plugin.UserProfileChecker", return_value=profile_checker)
        plugin = SteamPlugin(MagicMock(), writer, None)
        plugin.lost_authentication = Mock(return_value=None)
        type(plugin).persistent_cache = PropertyMock(return_value=cache)
        created_plugins.append(plugin)
        return plugin

    yield function

    for plugin in created_plugins:
        plugin.close()
        await plugin.wait_closed()


@pytest.fixture()
async def plugin(create_plugin):
    return create_plugin()


@pytest.fixture
def create_plugin_with_backend(mocker, create_plugin):
    DONT_PATCH = sentinel

    def fn(initial_mode=DONT_PATCH, fallback_mode=DONT_PATCH, connected_on_version: str = __version__, **kwargs):
        """
        :param connected_on_version     Version on which plugin was connected for the first time.
                                        Required to emulate stored state.
        """

        if initial_mode != DONT_PATCH:
            mocker.patch("plugin.BackendConfiguration.initial_mode",
                new_callable=PropertyMock(return_value=initial_mode))
        if fallback_mode != DONT_PATCH:
            mocker.patch("plugin.BackendConfiguration.fallback_mode",
                new_callable=PropertyMock(return_value=fallback_mode))

        cache = kwargs.setdefault("cache", {})
        if connected_on_version and not connected_on_version.startswith('0'):
            cache.setdefault(AUTH_SETUP_ON_VERSION__CACHE_KEY, connected_on_version)

        plugin = create_plugin(**kwargs)
        plugin.handshake_complete()  # loads initial backend
        return plugin
    return fn


@pytest.fixture
def create_authenticated_plugin_with_backend(create_plugin_with_backend):
    async def fn(*args, **kwargs):
        plugin = create_plugin_with_backend(*args, **kwargs)
        await plugin.authenticate(Mock(dict, name='stored_credentials'))
        return plugin
    return fn


@pytest.fixture
def register_mock_backend(mocker):
    """
    This fixture helps to introduce a new/artificial backend mode
    along with relevant `BackendInterface` mock implementation.
    Note: to unregister existing backend modes patch BACKEND_MAP with `clear=True`.
    """
    def fn(mode):
        """
        :returns mock of `BackendInterface` class
        """
        name = str(mode) + " backend mock" 
        instance_mock = Mock(spec=BackendInterface, name=name)
        instance_mock.authenticate = AsyncMock()
        class_mock = Mock(return_value=instance_mock, name=f"{name} class")
        mocker.patch.dict("plugin.BACKEND_MAP", {
            mode: class_mock
        })
        return class_mock
    return fn


@pytest.fixture
def patch_config_location(tmp_path, mocker):
    def fn(filename="steam_user_config.ini") -> pathlib.Path:
        tmp_config_path = tmp_path / filename
        return mocker.patch("plugin.USER_CONFIG_LOCATION", tmp_config_path)

    return fn


# load nested conftest files
# fixtures and hooks are applied in the relevant package scope only
pytest_plugins = ('tests.tests_public_profiles', 'tests.tests_steam_network')
