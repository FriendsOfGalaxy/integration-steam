from galaxy.api.types import UserInfo
from galaxy.api.errors import AuthenticationRequired
import pytest

from steam_network.protocol.steam_types import ProtoUserInfo, EPersonaState


@pytest.mark.asyncio
async def test_not_authenticated(plugin):
    with pytest.raises(AuthenticationRequired):
        await plugin.get_friends()


@pytest.mark.asyncio
async def test_no_friends(authenticated_plugin, websocket_client):
    websocket_client.get_friends.return_value = []
    websocket_client.get_friends_info.return_value = {}
    websocket_client.get_friends_nicknames.return_values = {}

    assert [] == await authenticated_plugin.get_friends()


@pytest.mark.asyncio
async def test_multiple_friends(authenticated_plugin, websocket_client):
    ids = ["76561198040630463", "76561198053830887"]
    websocket_client.get_friends.return_value = ids
    websocket_client.get_friends_info.return_value = {
        "76561198040630463": ProtoUserInfo(
            name="Test1",
            avatar_hash=b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00",
            state=EPersonaState.Invisible,
            game_id=0,
            game_name="",
            rich_presence={},
        ),
        "76561198053830887": ProtoUserInfo(
            name="Test2",
            avatar_hash=b"\x22\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x11",
            state=None,
            game_id=None,
            game_name=None,
            rich_presence=None,
        ),
    }
    websocket_client.get_friends_nicknames.return_value = {}
    result = await authenticated_plugin.get_friends()
    assert result == [
        UserInfo(
            "76561198040630463",
            "Test1",
            "https://steamcdn-a.akamaihd.net/steamcommunity/public/images/avatars/fe/fef49e7fa7e1997310d705b2a6158ff8dc1cdfeb_full.jpg",
            "https://steamcommunity.com/profiles/76561198040630463",
        ),
        UserInfo(
            "76561198053830887",
            "Test2",
            "https://steamcdn-a.akamaihd.net/steamcommunity/public/images/avatars/22/2200000000000000000000000000000000000011_full.jpg",
            "https://steamcommunity.com/profiles/76561198053830887",
        ),
    ]

    websocket_client.get_friends_info.assert_called_once_with(ids)


@pytest.mark.asyncio
async def test_multiple_friends_with_nicknames(authenticated_plugin, websocket_client):
    ids = ["76561198040630463", "76561198053830887"]
    websocket_client.get_friends.return_value = ids
    websocket_client.get_friends_info.return_value = {
        "76561198040630463": ProtoUserInfo(
            name="Test1",
            avatar_hash=b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00",
            state=EPersonaState.Invisible,
            game_id=0,
            game_name="",
            rich_presence={},
        ),
        "76561198053830887": ProtoUserInfo(
            name="Test2",
            avatar_hash=b"\x22\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x11",
            state=None,
            game_id=None,
            game_name=None,
            rich_presence=None,
        ),
    }
    websocket_client.get_friends_nicknames.return_value = {
        "76561198053830887": "nickname"
    }
    result = await authenticated_plugin.get_friends()
    assert result == [
        UserInfo(
            "76561198040630463",
            "Test1",
            "https://steamcdn-a.akamaihd.net/steamcommunity/public/images/avatars/fe/fef49e7fa7e1997310d705b2a6158ff8dc1cdfeb_full.jpg",
            "https://steamcommunity.com/profiles/76561198040630463",
        ),
        UserInfo(
            "76561198053830887",
            "Test2 (nickname)",
            "https://steamcdn-a.akamaihd.net/steamcommunity/public/images/avatars/22/2200000000000000000000000000000000000011_full.jpg",
            "https://steamcommunity.com/profiles/76561198053830887",
        ),
    ]

    websocket_client.get_friends_info.assert_called_once_with(ids)
