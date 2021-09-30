from unittest.mock import Mock
import pytest

from async_mock import AsyncMock


FIRST_SETUP_VERSION_CACHE = "auth_setup_on_version"


@pytest.mark.parametrize("initial_version", [
    "0.53",
    "1.53",
    "2.2.10",
])
async def test_ensure_version_is_cached_on_pass_login_credentials(
    create_plugin_with_backend,
    register_mock_backend,
    initial_version,
    mocker,
):
    current_plugin_version = "2.2.10"
    mocker.patch("plugin.__version__", current_plugin_version)
    backend = register_mock_backend("A").return_value
    backend.pass_login_credentials = AsyncMock(return_value=Mock(name="auth result"))
    plugin = create_plugin_with_backend("A", connected_on_version=initial_version)

    await plugin.pass_login_credentials(
        Mock(str, name="step"),
        Mock(dict, name="credentials"),
        Mock(dict, name="cookies")
    )
    
    assert plugin.persistent_cache[FIRST_SETUP_VERSION_CACHE] == current_plugin_version


async def test_do_not_cache_version_on_authenticate(
    create_plugin_with_backend,
    register_mock_backend,
    mocker
):
    current_plugin_version = "2.2.10"
    initial_version = "1.2.9"
    mocker.patch("plugin.__version__", current_plugin_version)
    backend = register_mock_backend("A").return_value
    backend.authenticate = AsyncMock(return_value=Mock(name="auth result"))
    plugin = create_plugin_with_backend("A", connected_on_version=initial_version)

    await plugin.authenticate(stored_credentials=Mock(name='stored_credentials'))
    
    plugin.persistent_cache[FIRST_SETUP_VERSION_CACHE] == initial_version
