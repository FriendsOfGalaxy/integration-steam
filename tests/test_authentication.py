import pytest
import re
from galaxy.api.types import Authentication, Cookie, NextStep
from galaxy.api.errors import UnknownBackendResponse, InvalidCredentials
from plugin import AUTH_PARAMS, LOGIN_URI, JS_PERSISTENT_LOGIN

PROFILE_URL = "https://url"


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
def stored_credentials(cookies):
    return {
        "cookies": cookies
    }

@pytest.fixture()
def auth_info():
    return ["19", "123", "Jan"]

@pytest.mark.asyncio
async def test_no_stored_credentials(
    backend_client,
    plugin,
    cookies,
    auth_info,
    stored_credentials,
    mocker
):
    steam_fake_cookie = Cookie(name="n", value="v")
    mocker.patch.object(plugin, "_create_two_factor_fake_cookie", return_value=steam_fake_cookie)
    assert NextStep(
        "web_session",
        AUTH_PARAMS,
        [steam_fake_cookie],
        {re.escape(LOGIN_URI): [JS_PERSISTENT_LOGIN]},
    ) == await plugin.authenticate()

    backend_client.get_profile.return_value = PROFILE_URL
    backend_client.get_profile_data.return_value = auth_info[0], auth_info[1], auth_info[2]

    store_credentials = mocker.patch.object(plugin, "store_credentials")
    assert Authentication(auth_info[0], auth_info[2]) == await plugin.pass_login_credentials(
        "random step name",
        {"end_uri": "https://steamcommunity.com/id/{}/goto".format(
            auth_info[0]
        )},
        cookies
    )
    store_credentials.assert_called_with(stored_credentials)

    backend_client.get_profile.assert_called_once_with()
    backend_client.get_profile_data.assert_called_once_with(PROFILE_URL)

@pytest.mark.asyncio
async def test_stored_credentials(
    backend_client,
    plugin,
    auth_info,
    stored_credentials
):
    backend_client.get_profile.return_value = PROFILE_URL
    backend_client.get_profile_data.return_value = auth_info[0], auth_info[1], auth_info[2]

    assert Authentication(auth_info[0], auth_info[2]) == await plugin.authenticate(stored_credentials)

    backend_client.get_profile.assert_called_with()
    backend_client.get_profile_data.assert_called_with(PROFILE_URL)

@pytest.mark.asyncio
async def test_invalid_stored_credentials(
    backend_client,
    plugin,
    stored_credentials,
    mocker
):
    backend_client.get_profile.side_effect = UnknownBackendResponse()
    lost_authentication = mocker.patch.object(plugin, "lost_authentication")
    with pytest.raises(InvalidCredentials):
        await plugin.authenticate(stored_credentials)
    lost_authentication.assert_not_called()

@pytest.mark.asyncio
async def test_stored_credentials_old_format(backend_client, plugin, auth_info):
    stored_credentials = {
        "cookies": {
            "cookie": "value"
        }
    }
    backend_client.get_profile.return_value = PROFILE_URL
    backend_client.get_profile_data.return_value = auth_info[0], auth_info[1], auth_info[2]

    assert Authentication(auth_info[0], auth_info[2]) == await plugin.authenticate(stored_credentials)

    backend_client.get_profile.assert_called_with()
    backend_client.get_profile_data.assert_called_with(PROFILE_URL)