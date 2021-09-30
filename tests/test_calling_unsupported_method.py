from unittest.mock import Mock
import enum
import functools
import inspect

import pytest
from galaxy.api.plugin import Plugin
from galaxy.api.consts import Platform

from backend_interface import BackendInterface


class BackendModeMock(enum.Enum):
    NothingImplementedMode = 'dummy'


class BackendInterfaceDummyImpl(BackendInterface):
    def __init__(self, *args, **kwargs):
        pass

    def authenticate(self, stored_credentials):
        pass

    def register_auth_lost_callback(self, callback):
        pass


@pytest.fixture
def patched_backend_map(mocker):
    BACKEND_MAP = {
        BackendModeMock.NothingImplementedMode: BackendInterfaceDummyImpl,
    }
    return mocker.patch.dict("plugin.BACKEND_MAP", BACKEND_MAP, clear=True)


class NothingImplementedPlugin(Plugin):
    def __init__(self):
        super().__init__(Platform.Test, "0.1", Mock(), Mock(), Mock())


def _iscoroutinefunction(object):
    """inspect.iscoroutinefunction backport for Python<3.8"""
    while isinstance(object, functools.partial):
        object = object.func
    return inspect.iscoroutinefunction(object)


async def result_or_exception_type(func):
    try:
        if _iscoroutinefunction(func):
            return await func()
        else:
            return func()
    except (AttributeError, NotImplementedError) as exc:
        return type(exc)


@pytest.mark.asyncio
async def test_calling_not_implemented_import_complete_method(create_plugin_with_backend, patched_backend_map):
    """
    Use case: normal Plugins API usage
    Expected: parent Plugin method is called as it is normally w/o using BackendInterface
    """
    plugin = create_plugin_with_backend(BackendModeMock.NothingImplementedMode)

    assert \
        await result_or_exception_type(plugin.game_times_import_complete) == \
        await result_or_exception_type(NothingImplementedPlugin().game_times_import_complete)


@pytest.mark.asyncio
async def test_calling_unsupported_async_method(create_plugin_with_backend, patched_backend_map):
    """
    Use case: switching backend to the one that has fewer features when plugin runs
    causes Galaxy to call methods unsupported in the new backend
    Expected: parent Plugin method is called as it is normally w/o using BackendInterface
    """
    plugin = create_plugin_with_backend(BackendModeMock.NothingImplementedMode)

    assert \
        await result_or_exception_type(plugin.get_owned_games) == \
        await result_or_exception_type(NothingImplementedPlugin().get_owned_games)


@pytest.mark.asyncio
async def test_calling_unsupported_prepare_context_method(create_plugin_with_backend, patched_backend_map):
    plugin = create_plugin_with_backend(BackendModeMock.NothingImplementedMode)
    user_ids = ['aid', 'bid']
    
    with pytest.raises(NotImplementedError):
        await plugin.prepare_user_presence_context(user_ids)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'method', [
        'tick', 'shutdown'
    ]
)
async def test_calling_plugin_methods(create_plugin_with_backend, patched_backend_map, method):
    plugin = create_plugin_with_backend(BackendModeMock.NothingImplementedMode)
    plugin_method = getattr(plugin, method)
    not_imp_plugin_method = getattr(NothingImplementedPlugin(), method)

    assert await result_or_exception_type(plugin_method) == await result_or_exception_type(not_imp_plugin_method)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'prepare_context_method, core_method',
    [
        ('prepare_game_times_context', 'get_game_time'),
        ('prepare_achievements_context', 'get_unlocked_achievements'),
        ('prepare_game_library_settings_context', 'get_game_library_settings'),
        ('prepare_os_compatibility_context', 'get_os_compatibility'),
        ('prepare_user_presence_context', 'get_user_presence'),
        ('prepare_subscription_games_context', 'get_subscription_games'),
    ]
)
async def test_not_implemented_prepare_context_method_for_supported_feature(
    create_plugin_with_backend,
    mocker,
    prepare_context_method,
    core_method,
):
    
    class BackendInterfaceDummyCopy(BackendInterfaceDummyImpl):
        pass

    setattr(BackendInterfaceDummyCopy, core_method, lambda *args: None)

    one_feature_backend_mode = 'one_feature'
    BACKEND_MAP = {
        one_feature_backend_mode: BackendInterfaceDummyCopy,
    }
    mocker.patch.dict("plugin.BACKEND_MAP", BACKEND_MAP, clear=True)
    plugin = create_plugin_with_backend(one_feature_backend_mode)
    importer_items = []
    
    try:
        await getattr(plugin, prepare_context_method)(importer_items)
    except (NotImplementedError, AttributeError) as e:
        pytest.fail(f"{e!r} should not be raised on start import method if a feature is implemented")
