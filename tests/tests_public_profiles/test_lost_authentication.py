import pytest

from galaxy.api.errors import (
    AccessDenied,
    AuthenticationRequired,
    UnknownBackendResponse,
)

from user_profile import ProfileDoesNotExist, ProfileIsNotPublic


pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    "profile_checker_exception", [ProfileIsNotPublic, ProfileDoesNotExist]
)
async def test_lost_authentication_on_profile_access_problem(
    profile_checker_exception,
    authenticated_plugin,
    steam_http_client,
    profile_checker,
):
    steam_http_client.get_games.side_effect = UnknownBackendResponse
    profile_checker.check_is_public_by_steam_id.side_effect = profile_checker_exception

    with pytest.raises(AccessDenied):
        await authenticated_plugin.get_owned_games()

    authenticated_plugin.lost_authentication.assert_called_once()


async def test_lost_authentication_not_called_when_not_authenticated(
    plugin, steam_http_client, profile_checker
):
    steam_http_client.get_games.side_effect = UnknownBackendResponse
    profile_checker.check_is_public_by_steam_id.side_effect = ProfileIsNotPublic

    with pytest.raises(AuthenticationRequired):
        await plugin.get_owned_games()

    plugin.lost_authentication.assert_not_called()
