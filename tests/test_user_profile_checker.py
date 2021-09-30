import pytest
from unittest.mock import Mock

from user_profile import UserProfileChecker, ProfileIsNotPublic, ParseError, ProfileDoesNotExist, \
    NotPublicGameDetailsOrUserHasNoGames


@pytest.fixture()
def user_name():
    return Mock(str)


@pytest.fixture()
def steam_id():
    return Mock(str)


@pytest.fixture()
def games():
    return '[{"appid": 123, "name": "NAME"}]'


@pytest.fixture()
def steam_html_response(games):
    def inner(games=games):
        return '''
            <div class="responsive_page_template_content" data-panel="{{&quot;autoFocus&quot;:true}}" >
                <script language="javascript">
                    var rgGames = {games};
                    var rgChangingGames = [];
                    var offerClientUninstall = false;
                    var profileLink = "https://steamcommunity.com/profiles/1234456789";
                    var personaName = "user1234456789";
                    var tab = "all";
                    var sessionID = "1234456789";
                </script>
            </div>
        '''.format(games=games)
    return inner


@pytest.mark.asyncio
async def test_profile_checker_with_public_username(http_client_mock, http_response_mock, user_name, steam_html_response):
    http_response_mock.text.return_value = steam_html_response()
    profile = UserProfileChecker(http_client_mock)

    assert await profile.check_is_public_by_custom_url(user_name)


@pytest.mark.asyncio
async def test_profile_checker_with_not_public_username(http_client_mock, http_response_mock):
    response = "<div class=responsive_page_template_content><div class=profile_private_info></div></div>"
    http_response_mock.text.return_value = response
    profile = UserProfileChecker(http_client_mock)

    with pytest.raises(ProfileIsNotPublic):
        assert await profile.check_is_public_by_custom_url(user_name)


@pytest.mark.asyncio
@pytest.mark.parametrize("games", [
    ('[{"appid": 123, "name": "CHAOS;CHILD"}]'),
    ('[{"appid": 124, "name": "Event[0]"}]'),
    pytest.param('[ {"appid": 124, "name": "game"} ]', id="spaces around"),
    pytest.param(
        r'[{"appid":453480,"name":"Shadowverse","logo":"https:\/\/cdn.akamai.steamstatic.com\/steam\/apps\/453480\/capsule_184x69.jpg","friendlyURL":false,"availStatLinks":{"achievements":false,"global_achievements":false,"stats":false,"gcpd":false,"leaderboards":false,"global_leaderboards":false},"hours_forever":"424","last_played":1526138198},{"appid":435150,"name":"Divinity: Original Sin 2","logo":"https:\/\/cdn.akamai.steamstatic.com\/steam\/apps\/435150\/capsule_184x69.jpg","friendlyURL":435150,"availStatLinks":{"achievements":true,"global_achievements":true,"stats":false,"gcpd":false,"leaderboards":false,"global_leaderboards":false},"hours_forever":"145","last_played":1541178619}]',
        id="chunk of real data"
    )
])
async def test_profile_checker_with_public_steam_id(http_client_mock, http_response_mock, steam_html_response, games):
    http_response_mock.text.return_value = steam_html_response(games=games)
    profile = UserProfileChecker(http_client_mock)

    assert await profile.check_is_public_by_steam_id(steam_id) == True


@pytest.mark.asyncio
async def test_profile_checker_with_not_public_steam_id(http_client_mock, http_response_mock):
    response = "<div class=responsive_page_template_content><div class=profile_private_info></div></div>"
    http_response_mock.text.return_value = response
    profile = UserProfileChecker(http_client_mock)

    with pytest.raises(ProfileIsNotPublic):
        assert await profile.check_is_public_by_steam_id(steam_id)


@pytest.mark.asyncio
@pytest.mark.parametrize('response', [
    '<div class=responsive_page_template_content></div>',
    '<div class=responsive_page_template_content><script language="SOME_CLASS">var rgGames = [];</div>',
    '<div class=some_class><script language="javascript">var rgGames = [];</div>',
    "<div class=some_class></div>",
    "bad_value",
])
async def test_profile_checker_with_unknown_response(http_client_mock, http_response_mock, response):
    http_response_mock.text.return_value = response
    profile = UserProfileChecker(http_client_mock)

    with pytest.raises(ParseError):
        assert await profile.check_is_public_by_steam_id(steam_id)


@pytest.mark.asyncio
async def test_does_profile_exist(http_client_mock, http_response_mock):
    response = """
        <div class=responsive_page_template_content>
            <div class="error_ctn">
            </div>
        </div>
    """
    http_response_mock.text.return_value = response
    profile = UserProfileChecker(http_client_mock)

    with pytest.raises(ProfileDoesNotExist):
        assert await profile.check_is_public_by_steam_id(steam_id)


@pytest.mark.asyncio
@pytest.mark.parametrize('games', [
    "[]",
    "[ ]",
])
async def test_public_profile_without_games(steam_html_response, http_client_mock, http_response_mock, games):
    http_response_mock.text.return_value = steam_html_response(games)
    profile = UserProfileChecker(http_client_mock)

    with pytest.raises(NotPublicGameDetailsOrUserHasNoGames):
        assert await profile.check_is_public_by_steam_id(steam_id)
