from galaxy.api.types import UserInfo
from galaxy.api.errors import AuthenticationRequired
import pytest

from public_profiles.steamcommunity_scrapper import SteamHttpClient


@pytest.mark.asyncio
async def test_not_authenticated(plugin):
    with pytest.raises(AuthenticationRequired):
        await plugin.get_friends()


@pytest.mark.asyncio
async def test_no_friends(authenticated_plugin, steam_http_client, steam_id):
    steam_http_client.get_friends.return_value = []

    assert [] == await authenticated_plugin.get_friends()
    steam_http_client.get_friends.assert_called_once_with(steam_id)


@pytest.mark.asyncio
async def test_multiple_friends(authenticated_plugin, steam_http_client, steam_id):
    steam_http_client.get_friends.return_value = [
        UserInfo("76561198040630463","crak","avatar","profile"),
        UserInfo("76561198053830887","Danpire","avatar2","profile2")
        ]


    result = await authenticated_plugin.get_friends()
    assert result == [
        UserInfo("76561198040630463","crak","avatar","profile"),
        UserInfo("76561198053830887","Danpire","avatar2","profile2")
    ]
    steam_http_client.get_friends.assert_called_once_with(steam_id)


@pytest.mark.asyncio
async def test_profile_parsing(http_client_mock, http_response_mock, steam_id):
    http_response_mock.text.return_value = '''
    <div class="profile_friends search_results" id="search_results">
        <div class="selectable friend_block_v2 persona offline " data-steamid="76561198056089614">
            <div class="indicator select_friend">
				<input class="select_friend_checkbox" type="checkbox">
			</div>

			<a class="selectable_overlay" data-container="#fr_112034288" href="https://steamcommunity.com/profiles/76561198056089614"></a>

			<div class="player_avatar friend_block_link_overlay online">
				<img src="https://steamcdn-a.akamaihd.net/steamcommunity/public/images/avatars/05/1_medium.jpg">
			</div>
            <div class="friend_block_content">На камазе!<br>
                <span class="friend_small_text"></span>
                <span class="friend_last_online_text">Last Online 189 days ago</span>
            </div>
        </div>
    </div>'''
    http_client_mock.get.return_value = http_response_mock

    assert [
        UserInfo(
            "76561198056089614",
            "На камазе!",
            "https://steamcdn-a.akamaihd.net/steamcommunity/public/images/avatars/05/1_medium.jpg",
            "https://steamcommunity.com/profiles/76561198056089614"
        )
    ] == await SteamHttpClient(http_client_mock).get_friends(steam_id)
