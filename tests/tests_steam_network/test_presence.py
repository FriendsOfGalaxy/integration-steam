from typing import NamedTuple
from dataclasses import dataclass

import pytest
from galaxy.api.errors import AuthenticationRequired, UnknownError
from galaxy.api.consts import PresenceState
from galaxy.api.types import UserPresence

from steam_network.presence import presence_from_user_info
from steam_network.protocol.consts import EPersonaState
from steam_network.protocol.steam_types import ProtoUserInfo


class TOKEN(NamedTuple):
    name: str
    value: str

@dataclass
class translations_cache_mock_dataclass:
    tokens = [TOKEN("#hero", "translated_hero")]

@dataclass
class translations_cache_parametrized_mock_dataclass:
    tokens = [TOKEN("#menu", "translated_menu{%param0%}"),
              TOKEN("#EN", "english")]

@dataclass
class translations_cache_values_fitting_partially_dataclass:
    tokens = [TOKEN("#PlayingAs", "Playing %Empire% (%Ethics1% %Ethics2%) in %Year%"),
              TOKEN("#PlayingAsNew", "Playing %Empire% (%Ethics%) in %Year%"),
              TOKEN("#PlayingAsNoEthics", "Playing %Empire% in %Year%")]

@pytest.mark.parametrize(
    "user_info,user_presence",
    [
        # Empty
        (
                ProtoUserInfo(),
                UserPresence(presence_state=PresenceState.Unknown)
        ),
        # Offline
        (
                ProtoUserInfo(state=EPersonaState.Offline),
                UserPresence(presence_state=PresenceState.Offline)
        ),
        # User online not playing a game
        (
                ProtoUserInfo(state=EPersonaState.Online, game_id=0, game_name="", rich_presence={}),
                UserPresence(presence_state=PresenceState.Online, game_id=None, game_title=None, in_game_status=None)
        ),
        # User online playing a game
        (
                ProtoUserInfo(state=EPersonaState.Online, game_id=1512, game_name="abc", rich_presence={"status": "menu"}),
                UserPresence(
                    presence_state=PresenceState.Online, game_id="1512", game_title="abc", in_game_status="menu"
                )
        ),
        # User playing a game with translatable rich presence
        (
            ProtoUserInfo(state=EPersonaState.Online, game_id=1512, game_name="abc", rich_presence={"status": "#hero"}),
            UserPresence(
                presence_state=PresenceState.Online, game_id="1512", game_title="abc", in_game_status="translated_hero"
            )
        ),
        # User playing a game with translatable rich presence which is parametrized
        (
            ProtoUserInfo(state=EPersonaState.Online, game_id=1513, game_name="abc", rich_presence={"status": "#menu", "num_params": 1, "param0": "#EN"}),
            UserPresence(
                presence_state=PresenceState.Online, game_id="1513", game_title="abc", in_game_status="translated_menu english"
            )
        ),
        # User playing a game with translatable rich presence and cache token that are partially fitting
        (
            ProtoUserInfo(state=EPersonaState.Online, game_id=1514, game_name="abc", rich_presence={'steam_display': '#PlayingAsNew', 'Empire': "Rihi'Nar Death Bringers", 'Ethics': 'Fanatic Xenophobe, Militarist', 'year': '2200'}),
            UserPresence(
                presence_state=PresenceState.Online, game_id="1514", game_title="abc", in_game_status="Playing Rihi'Nar Death Bringers (Fanatic Xenophobe, Militarist) in 2200"
            )
        )
    ]
)
@pytest.mark.asyncio
async def test_from_user_info(user_info, user_presence):
    assert await presence_from_user_info(user_info, {1512: translations_cache_mock_dataclass(),
                                                     1513: translations_cache_parametrized_mock_dataclass(),
                                                     1514: translations_cache_values_fitting_partially_dataclass()}) == user_presence


CONTEXT = {
    "76561198040630463": ProtoUserInfo(name="John", state=EPersonaState.Offline),
    "76561198053830887": ProtoUserInfo(name="Jan", state=EPersonaState.Online, game_id=124523113),
    "76561198053830888": ProtoUserInfo(name="Carol", state=EPersonaState.Online, game_id=123321, game_name="abc", rich_presence={'status': '#menuVariable'}),
    "76561198053830889": ProtoUserInfo(name="Carol", state=EPersonaState.Online, game_id=123321, game_name="abc", rich_presence={'status': 'menuSimple'})
}


@pytest.mark.asyncio
async def test_not_authenticated(plugin):
    with pytest.raises(AuthenticationRequired):
        await plugin.get_friends()


@pytest.mark.asyncio
async def test_prepare_user_presence_context(authenticated_plugin, websocket_client):
    websocket_client.get_friends_info.return_value = CONTEXT
    assert await authenticated_plugin.prepare_user_presence_context(
        ["76561198040630463", "76561198053830887"]
    ) == CONTEXT
    websocket_client.get_friends_info.assert_called_once_with(["76561198040630463", "76561198053830887"])


@pytest.mark.asyncio
async def test_get_user_presence_success(authenticated_plugin, websocket_client):
    presence = await authenticated_plugin.get_user_presence("76561198040630463", CONTEXT)
    assert presence == UserPresence(presence_state=PresenceState.Offline)

    presence = await authenticated_plugin.get_user_presence("76561198053830887", CONTEXT)
    assert presence == UserPresence(presence_state=PresenceState.Online, game_id="124523113")

    presence = await authenticated_plugin.get_user_presence("76561198053830888", CONTEXT)
    assert presence == UserPresence(presence_state=PresenceState.Online, game_id="123321", game_title="abc", in_game_status=None)

    presence = await authenticated_plugin.get_user_presence("76561198053830889", CONTEXT)
    assert presence == UserPresence(presence_state=PresenceState.Online, game_id="123321", game_title="abc", in_game_status='menuSimple')


@pytest.mark.asyncio
async def test_get_user_presence_not_friend(authenticated_plugin, websocket_client):
    with pytest.raises(UnknownError):
        await authenticated_plugin.get_user_presence("123151", {})



