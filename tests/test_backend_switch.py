from unittest.mock import Mock

import pytest
from galaxy.api.errors import BackendError, InvalidCredentials, AccessDenied, NetworkError
from galaxy.api.types import Authentication

from backend_configuration import BackendMode
from backend_interface import BackendInterface


pytestmark = pytest.mark.asyncio


async def test_create_plugin_with_backend_fixture(
    create_plugin_with_backend,
    register_mock_backend,
):
    backend_mode = 'Dummy Mode'
    backend_cls = register_mock_backend(backend_mode)

    backend_cls.assert_not_called()
    create_plugin_with_backend(backend_mode) 
    backend_cls.assert_called_once()


# test switching a backend on authenticate

@pytest.mark.parametrize("error", [
    InvalidCredentials,
    AccessDenied,
    # Catching all unexpected errors is needed as a consequence of a project decision NOT to cache
    # current backend state and ALWAYS try to connect to `initial` backend on plugin start instead.
    # This way we avoid being trapped in not-working backend on plugin start,
    # but it may reveal incosistencies between backends when switching between them 
    # in case of temporal problems with the `initial` one.
    BackendError,
    pytest.param(Exception, id="Any other unexpected exception")
])
async def test_switch_to_fallback_backend_during_authentication(
    create_plugin_with_backend,
    register_mock_backend,
    error,
):
    backend_a = register_mock_backend("A").return_value
    backend_b = register_mock_backend("B").return_value
    backend_a.authenticate.side_effect = error()
    backend_b.authenticate.return_value = 'ok'

    plugin = create_plugin_with_backend(initial_mode="A", fallback_mode="B")
    response = await plugin.authenticate()

    backend_a.authenticate.assert_called_once()
    backend_b.authenticate.assert_called_once()
    assert 'ok' == response


@pytest.mark.parametrize("error", [
    NetworkError
])
async def test_do_not_switch_backend_during_authentication_on_error(
    create_plugin_with_backend,
    register_mock_backend,
    error
):
    backend_a = register_mock_backend("A").return_value
    backend_b_cls = register_mock_backend("B")
    backend_a.authenticate.side_effect = error

    plugin = create_plugin_with_backend(initial_mode="A", fallback_mode="B")
    with pytest.raises(error):
       await plugin.authenticate()
    backend_b_cls.assert_not_called()


async def test_switch_to_fallback_backend_during_authentication_and_then_raise(
    create_plugin_with_backend,
    register_mock_backend,
):
    backend_a = register_mock_backend("A").return_value
    backend_b = register_mock_backend("B").return_value
    exception = AccessDenied
    backend_a.authenticate.side_effect = InvalidCredentials()
    backend_b.authenticate.side_effect = exception()

    plugin = create_plugin_with_backend(initial_mode="A", fallback_mode="B")
    with pytest.raises(exception):
        await plugin.authenticate()

    backend_a.authenticate.assert_called_once()
    backend_b.authenticate.assert_called_once()


# testing switching a backend on authorization lost handler

class DummyBackendWithAuthLostCallback(BackendInterface):
    def __init__(self, *args, **kwargs) -> None:
        self._auth_lost_callback = None

    def register_auth_lost_callback(self, callback):
        self._auth_lost_callback = callback
    
    async def authenticate(self, credentials):
        pass
    
    def emulate_loosing_authorization(self):
        """public method specific for this class for the test purposes"""
        self._auth_lost_callback()


async def test_lost_authentication_callback_called_once(
    register_mock_backend,
    create_authenticated_plugin_with_backend,
):
    initial_backend = DummyBackendWithAuthLostCallback()
    register_mock_backend("A").return_value = initial_backend
    fallback_backend_cls = register_mock_backend("B")

    plugin = await create_authenticated_plugin_with_backend(
        initial_mode="A", fallback_mode="B")

    initial_backend.emulate_loosing_authorization()

    fallback_backend_cls.assert_called_once()
    plugin.lost_authentication.assert_not_called()
    

async def test_lost_authentication_callback_called_from_fallback_backend(
    register_mock_backend,
    create_authenticated_plugin_with_backend,
):
    fallback_backend = DummyBackendWithAuthLostCallback()
    fallback_backend_cls = register_mock_backend("F")
    fallback_backend_cls.return_value = fallback_backend

    plugin = await create_authenticated_plugin_with_backend(
        initial_mode="F", fallback_mode="F")

    fallback_backend.emulate_loosing_authorization()

    plugin.lost_authentication.assert_called_once()
    

async def test_lost_authentication_callback_called_again_after_switching_to_fallback_backend(
    create_authenticated_plugin_with_backend,
    register_mock_backend,
):
    initial_backend = DummyBackendWithAuthLostCallback()
    register_mock_backend("C").return_value = initial_backend
    fallback_backend = DummyBackendWithAuthLostCallback()
    register_mock_backend("F").return_value = fallback_backend

    plugin = await create_authenticated_plugin_with_backend(
        initial_mode="C", fallback_mode="F")

    initial_backend.emulate_loosing_authorization()
    plugin.lost_authentication.assert_not_called()

    fallback_backend.emulate_loosing_authorization()
    plugin.lost_authentication.assert_called_once()


async def test_lost_authentication_when_backend_was_switched_on_authentication_already(
    create_plugin_with_backend,
    register_mock_backend,
):
    initial_backend = register_mock_backend("A").return_value
    initial_backend.authenticate.side_effect = InvalidCredentials
    
    fallback_backend = DummyBackendWithAuthLostCallback()
    fallback_backend_cls = register_mock_backend("B")
    fallback_backend_cls.return_value = fallback_backend

    plugin = create_plugin_with_backend(initial_mode="A", fallback_mode="B")
    await plugin.authenticate(Mock(dict, name='stored_credentials'))
    assert fallback_backend_cls.call_count == 1, \
        "precondition failed: backend not switched on authentication"

    fallback_backend.emulate_loosing_authorization()

    plugin.lost_authentication.assert_called_once()


# test SteamPlugin behavior for real backends

@pytest.fixture
def steam_network_backend(register_mock_backend):
    return register_mock_backend(BackendMode.SteamNetwork).return_value


@pytest.fixture
def public_profiles_backend(register_mock_backend):
    return register_mock_backend(BackendMode.PublicProfiles).return_value


@pytest.fixture
def persona_name():
    return "steam persona name"


async def test_failed_authentication_on_default_mode_with_default_fallback(
    create_plugin_with_backend,
    steam_network_backend,
    public_profiles_backend,
    steam_id,
    persona_name,
):
    """
    On loosing access with default SteamNetwork mode, we switch to PublicProfiles
    """
    steam_network_backend.authenticate.side_effect = InvalidCredentials("eresult: 5")
    public_profiles_backend.authenticate.return_value = Authentication(steam_id, persona_name)

    plugin = create_plugin_with_backend()  # letting default backend to load
    result = await plugin.authenticate(stored_credentials=Mock())

    assert result == Authentication(steam_id, persona_name)


async def test_failed_authentication_on_steam_network_with_no_fallback_mode(
    create_plugin_with_backend,
    steam_network_backend,
):
    steam_network_backend.authenticate.side_effect = InvalidCredentials("eresult: 5")

    plugin = create_plugin_with_backend(
        initial_mode=BackendMode.SteamNetwork,
        fallback_mode=None
    )
    with pytest.raises(InvalidCredentials):
        await plugin.authenticate()


async def test_failed_authentication_on_public_profiles_with_no_fallback_mode(
    create_plugin_with_backend,
    public_profiles_backend,
):
    public_profiles_backend.authenticate.side_effect = AccessDenied("profile is private")

    plugin = create_plugin_with_backend(
        initial_mode=BackendMode.PublicProfiles,
        fallback_mode=None
    )
    with pytest.raises(AccessDenied):
        await plugin.authenticate()
