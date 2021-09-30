"""Fixtures for testing behaviors in when relying on user public profile only."""

from unittest.mock import MagicMock

import pytest

from tests.async_mock import AsyncMock
from plugin import BackendMode


@pytest.fixture
def steam_http_client():
    mock = MagicMock(spec=(), name='steam_http_client__public_profiles')
    mock.get_profile = AsyncMock()
    mock.get_profile_data = AsyncMock()
    mock.get_games = AsyncMock()
    mock.get_achievements = AsyncMock()
    mock.get_friends = AsyncMock()
    mock.get_authentication_data = AsyncMock()
    mock.get_owned_ids = AsyncMock()
    mock.get_steamcommunity_response_status = AsyncMock()
    return mock


@pytest.fixture
def profile_checker():
    mock = MagicMock(spec=())
    mock.check_is_public_by_steam_id = AsyncMock()
    return mock


@pytest.fixture()
async def create_pp_plugin(
    create_plugin_with_backend, mocker, steam_http_client, profile_checker
):
    default_patches = [
        dict(target='backend_public_profiles.SteamHttpClient', return_value=steam_http_client),
        dict(target='backend_public_profiles.UserProfileChecker', return_value=profile_checker)
    ]
    def function(cache, patches=default_patches):
        for patch_kwargs in patches:
            mocker.patch(**patch_kwargs)
        plugin = create_plugin_with_backend(BackendMode.PublicProfiles, cache=cache)
        return plugin

    return function


@pytest.fixture()
async def plugin(create_pp_plugin):
    persistent_cache = {}
    return create_pp_plugin(persistent_cache)


@pytest.fixture()
async def create_authenticated_pp_plugin(create_pp_plugin, steam_http_client, steam_id, login, miniprofile):
    async def function(cache):
        plugin = create_pp_plugin(cache)
        steam_http_client.get_profile.return_value = "http://url"
        steam_http_client.get_profile_data.return_value = miniprofile, login
        credentials = {
            "steam_id": steam_id
        }
        await plugin.authenticate(credentials)
        return plugin

    return function


@pytest.fixture()
async def authenticated_plugin(create_authenticated_pp_plugin):
    persistent_cache = {}
    return await create_authenticated_pp_plugin(persistent_cache)
