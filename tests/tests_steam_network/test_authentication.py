from unittest.mock import Mock

import pytest
from galaxy.api.types import NextStep, Authentication
from galaxy.unittest.mock import async_return_value

from steam_network.protocol_client import UserActionRequired
from user_profile import ProfileIsNotPublic, NotPublicGameDetailsOrUserHasNoGames


pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize('end_uri', [
    ".*login_finished.*?username=aaa&password=bbb",
    ".*two_factor_mobile_finished.*?code=aaa",
    ".*two_factor_mail_finished.*?code=aaa",
])
async def test_public_profile_prompt_with_public_profile_with_2fa(
    plugin, profile_checker, mocker, end_uri
):
    profile_checker.check_is_public_by_steam_id.return_value = True
    mocker.patch('backend_steam_network.SteamNetworkBackend._get_websocket_auth_step',
                 return_value=async_return_value(UserActionRequired.NoActionRequired))
    plugin._SteamPlugin__backend._auth_data = [Mock(str), Mock(str)]
    result = await plugin.pass_login_credentials(
        Mock(str, name="step_name"),
        {"end_uri": f"{end_uri}"},
        {}
    )
    assert isinstance(result, Authentication)


@pytest.mark.parametrize('public_state, retry, expected_result', [
    pytest.param(True, False, Authentication, id="user with public profile clicked 'Skip' button"),
    pytest.param(ProfileIsNotPublic, False, Authentication, id="user with private profile clicked 'Skip' button"),
    pytest.param(ProfileIsNotPublic, True, NextStep, id="user with private profile clicked 'Retry' button"),
])
async def test_public_profile_prompt_buttons(
    plugin, profile_checker, public_state, retry, expected_result
):
    profile_checker.check_is_public_by_steam_id.side_effect = public_state

    result = await plugin.pass_login_credentials(
        Mock(str, name="step_name"),
        {"end_uri": f".*public_prompt_finished.*?public_profile_fallback={retry}"},
        {}
    )
    assert isinstance(result, expected_result)


@pytest.mark.parametrize('public_state, retry', [
    pytest.param(ProfileIsNotPublic, True),
])
async def test_public_profile_nextstep_end_uri(
    plugin, profile_checker, public_state, retry
):
    profile_checker.check_is_public_by_steam_id.side_effect = public_state

    result = await plugin.pass_login_credentials(
        Mock(str, name="step_name"),
        {"end_uri": f".*public_prompt_finished.*?public_profile_fallback={retry}"},
        {}
    )
    assert result.auth_params.get("end_uri_regex") == ".*public_prompt_finished.*"


@pytest.mark.parametrize('end_uri', [
    ".*login_finished.*?username=aaa&password=bbb",
    ".*two_factor_mobile_finished.*?code=aaa",
    ".*two_factor_mail_finished.*?code=aaa",
])
async def test_public_profile_prompt_for_not_public_profile(
    plugin, profile_checker, mocker, end_uri
):
    profile_checker.check_is_public_by_steam_id.side_effect = ProfileIsNotPublic
    mocker.patch('backend_steam_network.SteamNetworkBackend._get_websocket_auth_step',
                 return_value=async_return_value(UserActionRequired.NoActionRequired))
    plugin._SteamPlugin__backend._auth_data = [Mock(str), Mock(str)]
    result = await plugin.pass_login_credentials(
        Mock(str, name="step_name"),
        {"end_uri": f"{end_uri}a"},
        {}
    )
    assert isinstance(result, NextStep)
    assert "pp_prompt__profile_is_not_public" in result.auth_params["start_uri"]


@pytest.mark.parametrize('end_uri', [
    ".*login_finished.*?username=aaa&password=bbb",
    ".*two_factor_mobile_finished.*?code=aaa",
    ".*two_factor_mail_finished.*?code=aaa",
    ".*public_prompt_finished.*?public_profile_fallback=true",
])
@pytest.mark.asyncio
async def test_public_profile_prompt_for_not_public_game_details_or_empty_games_list(
    plugin, profile_checker, mocker, end_uri
):
    profile_checker.check_is_public_by_steam_id.side_effect = NotPublicGameDetailsOrUserHasNoGames
    mocker.patch('backend_steam_network.SteamNetworkBackend._get_websocket_auth_step',
                 return_value=async_return_value(UserActionRequired.NoActionRequired))
    plugin._SteamPlugin__backend._auth_data = [Mock(str), Mock(str)]
    result = await plugin.pass_login_credentials(
        "random step name",
        {"end_uri": f"{end_uri}"},
        {}
    )
    assert isinstance(result, NextStep)
    assert "pp_prompt__not_public_game_details_or_user_has_no_games" in result.auth_params["start_uri"]


@pytest.mark.parametrize('end_uri', [
    ".*login_finished.*?username=aaa&password=bbb",
    ".*two_factor_mobile_finished.*?code=aaa",
    ".*two_factor_mail_finished.*?code=aaa",
    ".*public_prompt_finished.*?public_profile_fallback=true",
])
@pytest.mark.asyncio
async def test_public_profile_prompt_on_unknown_error_during_checking_profile_privacy(
    plugin, profile_checker, mocker, end_uri
):
    profile_checker.check_is_public_by_steam_id.side_effect = Exception
    mocker.patch('backend_steam_network.SteamNetworkBackend._get_websocket_auth_step',
                 return_value=async_return_value(UserActionRequired.NoActionRequired))
    plugin._SteamPlugin__backend._auth_data = [Mock(str), Mock(str)]
    result = await plugin.pass_login_credentials(
        "random step name",
        {"end_uri": f"{end_uri}"},
        {}
    )
    assert isinstance(result, NextStep)
    assert "pp_prompt__unknown_error" in result.auth_params["start_uri"]
