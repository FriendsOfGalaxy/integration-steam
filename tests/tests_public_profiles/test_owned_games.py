from galaxy.api.types import Game, LicenseInfo
from galaxy.api.consts import LicenseType
from galaxy.api.errors import AuthenticationRequired
import pytest

@pytest.mark.asyncio
async def test_not_authenticated(plugin):
    with pytest.raises(AuthenticationRequired):
        await plugin.get_owned_games()

@pytest.mark.asyncio
async def test_no_games(authenticated_plugin, steam_http_client, steam_id):
    steam_http_client.get_games.return_value = []

    result = await authenticated_plugin.get_owned_games()
    assert result == []
    steam_http_client.get_games.assert_called_with(steam_id)

@pytest.mark.asyncio
async def test_multiple_games(authenticated_plugin, steam_http_client, steam_id):
    # only fields important for the logic
    steam_http_client.get_games.return_value = [
        {
            "appid": 281990,
            "name": "Stellaris"
        },
        {
            "appid": 236850,
            "name": "Europa Universalis IV"
        }
    ]

    result = await authenticated_plugin.get_owned_games()
    assert result == [
        Game("281990", "Stellaris", [], LicenseInfo(LicenseType.SinglePurchase, None)),
        Game("236850", "Europa Universalis IV", [], LicenseInfo(LicenseType.SinglePurchase, None))
    ]
    steam_http_client.get_games.assert_called_with(steam_id)
