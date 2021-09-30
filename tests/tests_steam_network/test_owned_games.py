from unittest.mock import MagicMock, Mock
from typing import Iterable

import pytest
from galaxy.unittest.mock import AsyncMock
from galaxy.api.types import Game, LicenseInfo
from galaxy.api.consts import LicenseType
from galaxy.api.errors import AuthenticationRequired

from steam_network.games_cache import App


async def async_gen(items: Iterable):
    for i in items:
        yield i


@pytest.fixture
def games_cache_mock():
    mock = MagicMock(spec=())
    mock.dump = Mock()
    mock.wait_ready = AsyncMock()
    return mock


@pytest.fixture
async def authenticated_plugin(mocker, games_cache_mock, create_authenticated_sn_plugin):
    """Overridden version of the fixture with patched games_cache"""
    mocker.patch('backend_steam_network.GamesCache', return_value=games_cache_mock)
    return await create_authenticated_sn_plugin({})


@pytest.mark.asyncio
async def test_not_authenticated(plugin):
    with pytest.raises(AuthenticationRequired):
        await plugin.get_owned_games()


@pytest.mark.asyncio
async def test_no_games(games_cache_mock, authenticated_plugin):
    games_cache_mock.get_owned_games = MagicMock(return_value=async_gen([]))
    result = await authenticated_plugin.get_owned_games()
    assert result == []


@pytest.mark.asyncio
async def test_multiple_games(games_cache_mock, authenticated_plugin):
    games_cache_mock.get_owned_games = MagicMock(return_value=async_gen([
        App(appid="281990", title="Stellaris", type="game", parent=None),
        App(appid="236850", title="Europa Universalis IV", type="game", parent=None),
    ]))
    result = await authenticated_plugin.get_owned_games()
    assert result == [
        Game("281990", "Stellaris", [], LicenseInfo(LicenseType.SinglePurchase, None)),
        Game("236850", "Europa Universalis IV", [], LicenseInfo(LicenseType.SinglePurchase, None))
    ]
