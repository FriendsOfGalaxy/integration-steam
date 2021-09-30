from galaxy.api.types import GameTime
from galaxy.api.errors import AuthenticationRequired
import pytest


@pytest.mark.asyncio
async def test_not_authenticated(plugin):
    with pytest.raises(AuthenticationRequired):
        await plugin.prepare_game_times_context(["13", "23"])


@pytest.mark.asyncio
async def test_import(authenticated_plugin):
    authenticated_plugin._backend._times_cache = {"281990": {'time_played': 78, 'last_played': 123},
                                         "236850": {'time_played': 86820, 'last_played':321}}
    assert await authenticated_plugin.get_game_time("236850", None) == GameTime("236850", 86820, 321)
    assert await authenticated_plugin.get_game_time("281990", None) == GameTime("281990", 78, 123)


@pytest.mark.asyncio
async def test_missing_game_time(authenticated_plugin):
    authenticated_plugin._backend._times_cache = {}
    game_time = await authenticated_plugin.get_game_time("281990", None)
    assert game_time == GameTime("281990", None, None)
