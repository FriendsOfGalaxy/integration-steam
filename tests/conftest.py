from unittest.mock import MagicMock

import pytest
from galaxy.unittest.mock import AsyncMock, async_return_value
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../output')))
from plugin import SteamPlugin


@pytest.fixture
def backend_client():
    mock = MagicMock(spec=())
    mock.get_profile = AsyncMock()
    mock.get_profile_data = AsyncMock()
    mock.get_games = AsyncMock()
    mock.get_achievements = AsyncMock()
    mock.get_friends = AsyncMock()
    mock.set_cookie_jar = MagicMock()
    mock.set_auth_lost_callback = MagicMock()
    mock.set_cookies_updated_callback = MagicMock()
    return mock


@pytest.fixture()
async def create_plugin(backend_client, mocker):
    created_plugins = []

    def function():
        writer = MagicMock(name="stream_writer")
        writer.drain.side_effect = lambda: async_return_value(None)

        mocker.patch("plugin.SteamHttpClient", return_value=backend_client)
        mocker.patch("plugin.local_games_list", return_value=[])
        plugin = SteamPlugin(MagicMock(), writer, None)
        created_plugins.append(plugin)
        return plugin

    yield function

    for plugin in created_plugins:
        await plugin.shutdown()


@pytest.fixture()
async def plugin(create_plugin):
    return create_plugin()


@pytest.fixture()
def steam_id():
    return "156"


@pytest.fixture()
def login():
    return "tester"


@pytest.fixture()
def miniprofile():
    return "123"


@pytest.fixture()
async def create_authenticated_plugin(create_plugin, backend_client, mocker):
    async def function(steam_id, login, miniprofile, cache):
        mocker.patch.object(SteamPlugin, "persistent_cache", new_callable=mocker.PropertyMock, return_value=cache)
        plugin = create_plugin()
        backend_client.get_profile.return_value = "http://url"
        backend_client.get_profile_data.return_value = steam_id, login, miniprofile
        credentials = {
            "cookies": [
                {
                    "name": "cookie",
                    "value": "value",
                    "domain": "steamcommunity.com",
                    "path": "/"
                }
            ]
        }
        plugin.handshake_complete()
        await plugin.authenticate(credentials)

        return plugin

    return function


@pytest.fixture()
async def authenticated_plugin(create_authenticated_plugin, steam_id, login, miniprofile):
    return await create_authenticated_plugin(steam_id, login, miniprofile, {})
