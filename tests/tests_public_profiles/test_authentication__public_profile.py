from unittest.mock import Mock
from urllib.parse import unquote
import base64

import pytest
from galaxy.api.types import Authentication, NextStep
from galaxy.api.errors import AccessDenied, UnknownBackendResponse

from user_profile import ProfileDoesNotExist, ProfileIsNotPublic


PROFILE_URL = "https://url"


@pytest.fixture()
def auth_params(plugin_root_dir):

    def inner(param):
        param = param
        return {
            "window_title": "Login to Steam",
            "window_width": 500,
            "window_height": 460,
            "start_uri": unquote((plugin_root_dir / 'public_profiles'  / 'custom_login' / f'index.html{param}').as_uri()),
            "end_uri_regex": '.*(login_finished|open_in_default_browser).*'
        }

    yield inner


@pytest.fixture()
def cookies():
    return [
        {
            "name": "cookie",
            "value": "value",
            "domain": "",
            "path": '/'
        }
    ]


@pytest.fixture()
def stored_credentials(cookies, steam_id):
    return {
        "cookies": cookies,
        "steam_id": steam_id
    }


@pytest.fixture()
def steam_id():
    return "123"


@pytest.fixture()
def user_name():
    return "Jan"


@pytest.fixture()
def authentication_result(steam_id, user_name):
    USER_NAME_SUFFIX = " (public)"
    return Authentication(steam_id, user_name + USER_NAME_SUFFIX)


@pytest.mark.asyncio
async def test_no_stored_credentials_provided(
    steam_http_client,
    plugin,
    cookies,
    steam_id,
    user_name,
    auth_params,
    profile_checker,
    authentication_result,
):
    assert NextStep("web_session", auth_params("?view=login"), None, None) == await plugin.authenticate()

    steam_http_client.get_profile.return_value = PROFILE_URL
    steam_http_client.get_profile_data.return_value = steam_id, user_name
    profile_checker.check_is_public_by_steam_id.return_value = True

    result = await plugin.pass_login_credentials(
        "random step name",
        {"end_uri": f".*login_finished.*?steam_id={steam_id}"},
        cookies
    )

    assert result == authentication_result
    steam_http_client.get_profile_data.assert_called_once_with(f"https://steamcommunity.com/profiles/{steam_id}")


@pytest.mark.asyncio
async def test_authentication_with_stored_credentials(
    steam_http_client,
    plugin,
    stored_credentials,
    steam_id,
    user_name,
    authentication_result,
):
    steam_http_client.get_profile.return_value = PROFILE_URL
    steam_http_client.get_profile_data.return_value = steam_id, user_name

    result = await plugin.authenticate(stored_credentials)

    assert result == authentication_result
    steam_http_client.get_profile_data.assert_called_once_with(f"https://steamcommunity.com/profiles/{steam_id}")


@pytest.mark.asyncio
async def test_invalid_stored_credentials(
    steam_http_client,
    plugin,
    mocker
):
    steam_http_client.get_profile.side_effect = UnknownBackendResponse()
    lost_authentication = mocker.patch.object(plugin, "lost_authentication")
    lost_authentication.assert_not_called()


@pytest.mark.asyncio
async def test_provided_not_public_profile(
    plugin,
    cookies,
    auth_params,
    steam_id,
    profile_checker
):
    assert NextStep("web_session", auth_params("?view=login"), None, None) == await plugin.authenticate()

    profile_checker.check_is_public_by_steam_id.side_effect = ProfileIsNotPublic()

    assert NextStep("web_session", auth_params("?view=login&profile_is_not_public=true"), None, None) == await plugin.pass_login_credentials(
        "random step name",
        {"end_uri": f".*login_finished.*?steam_id={steam_id}"},
        cookies
    )

    
@pytest.mark.asyncio
@pytest.mark.parametrize("profile_problem", [
    ProfileIsNotPublic,
    ProfileDoesNotExist,
])
async def test_authenticate_with_credentials_raises_on_not_public_profile(
    plugin,
    stored_credentials,
    profile_checker,
    profile_problem,
    steam_http_client,
):
    profile_checker.check_is_public_by_steam_id.side_effect = profile_problem
    steam_http_client.get_profile_data.return_value = Mock(), Mock()

    with pytest.raises(AccessDenied):
        await plugin.authenticate(stored_credentials)


@pytest.mark.asyncio
async def test_authenticate_with_credentials_from_steam_network_backend(
    plugin,
    steam_id,
    steam_http_client,
    user_name,
    authentication_result,
):
    def get_profile_data(url):
        if steam_id in url:
            return Mock(), user_name
        else:
            raise UnknownBackendResponse()

    steam_http_client.get_profile_data.side_effect = get_profile_data
    steam_network_stored_credentials = {
        "steam_id": base64.b64encode(steam_id.encode('utf-8')).decode('utf-8'),
        "token": "Y2Jh",  # omitting other usused values
    }

    result = await plugin.authenticate(steam_network_stored_credentials)
    
    assert result == authentication_result
