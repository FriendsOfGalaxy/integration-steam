from galaxy.api.types import GameTime
from galaxy.api.errors import AuthenticationRequired, UnknownError
import pytest


@pytest.mark.asyncio
async def test_not_authenticated(plugin):
    with pytest.raises(AuthenticationRequired):
        await plugin.prepare_game_times_context(["13", "23"])


@pytest.mark.asyncio
async def test_prepare_game_times_context(authenticated_plugin, steam_http_client):
    steam_http_client.get_games.return_value = [
        {
            "appid": 281990,
            "hours_forever": "1.3",
            "last_played": 1549385500
        },
        {
            "appid": 236850,
            "hours_forever": "1,447",
            "last_played": 1549385500
        }
    ]
    context = await authenticated_plugin.prepare_game_times_context(["281990", "236850"])
    assert context == {
        "236850": GameTime(game_id="236850", time_played=86820, last_played_time=1549385500),
        "281990": GameTime(game_id="281990", time_played=78, last_played_time=1549385500)
    }


@pytest.mark.asyncio
async def test_import(authenticated_plugin, steam_http_client):
    context = {
        "236850": GameTime(game_id="236850", time_played=86820, last_played_time=1549385500),
        "281990": GameTime(game_id="281990", time_played=78, last_played_time=1549385500)
    }
    assert await authenticated_plugin.get_game_time("281990", context) == GameTime("281990", 78, 1549385500)
    assert await authenticated_plugin.get_game_time("236850", context) == GameTime("236850", 86820, 1549385500)


@pytest.mark.asyncio
async def test_missing_game_time(authenticated_plugin, steam_http_client):
    context = {}
    with pytest.raises(UnknownError):
        await authenticated_plugin.get_game_time("281990", context)
