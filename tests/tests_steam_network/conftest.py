from unittest.mock import MagicMock

import pytest
from galaxy.unittest.mock import AsyncMock

from plugin import BackendMode


@pytest.fixture
def websocket_client():
    mock = MagicMock(spec=())
    mock.start = AsyncMock()
    mock.close = AsyncMock()
    mock.wait_closed = AsyncMock()
    mock.run = AsyncMock()
    mock.get_friends_info = AsyncMock()
    mock.get_friends = AsyncMock()
    mock.get_friends_nicknames = AsyncMock()
    mock.refresh_game_stats = AsyncMock()
    mock.communication_queues = {'plugin': AsyncMock(), 'websocket': AsyncMock()}
    return mock


@pytest.fixture
def create_sn_plugin(create_plugin_with_backend, mocker, websocket_client):
    """sn stands for SteamNetwork"""
    async def function(cache):
        mocker.patch('backend_steam_network.WebSocketClient', return_value=websocket_client)
        plugin = create_plugin_with_backend(BackendMode.SteamNetwork, cache=cache)
        return plugin

    return function


@pytest.fixture
async def plugin(create_sn_plugin):
    return await create_sn_plugin(cache={})


@pytest.fixture
def credentials():
    return {
        "account_id": "MTIz",
        "account_username": "YWJj",
        "persona_name": "YWJj",
        "sentry": "Y2Jh",
        "steam_id": "MTIz",
        "token": "Y2Jh"
    }


@pytest.fixture
async def create_authenticated_sn_plugin(create_sn_plugin, credentials):
    async def function(cache):
        plugin = await create_sn_plugin(cache)
        plugin._backend._user_info_cache.initialized.wait = AsyncMock()
        await plugin.authenticate(credentials)
        return plugin

    return function


@pytest.fixture()
async def authenticated_plugin(create_authenticated_sn_plugin):
    return await create_authenticated_sn_plugin({})
