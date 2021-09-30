from unittest.mock import MagicMock, ANY, call, Mock
import ssl
import asyncio

import pytest
import websockets
from galaxy.api.errors import (
    AccessDenied,
    BackendNotAvailable,
    BackendTimeout,
    BackendError,
    InvalidCredentials,
    NetworkError,
)
from galaxy.unittest.mock import async_return_value, skip_loop, AsyncMock

from steam_network.websocket_client import WebSocketClient, RECONNECT_INTERVAL_SECONDS
from steam_network.websocket_list import WebSocketList
from steam_network.protocol_client import UserActionRequired
from steam_network.friends_cache import FriendsCache
from steam_network.games_cache import GamesCache
from steam_network.stats_cache import StatsCache
from steam_network.times_cache import TimesCache
from steam_network.user_info_cache import UserInfoCache
from steam_network.ownership_ticket_cache import OwnershipTicketCache


ACCOUNT_NAME = "john"
PASSWORD = "testing123"
TWO_FACTOR = "AbCdEf"


async def async_raise(error, loop_iterations_delay=0):
    if loop_iterations_delay > 0:
        await skip_loop(loop_iterations_delay)
    raise error


async def aiter(seq):
    for i in seq:
        yield i


async def aiter_raise(exc):
    raise exc
    yield


@pytest.fixture
def websocket_list():
    websocket_list = MagicMock(WebSocketList)
    return websocket_list


@pytest.fixture()
def protocol_client(mocker):
    protocol_client = mocker.patch(
        "steam_network.websocket_client.ProtocolClient"
    ).return_value
    protocol_client.get_steam_app_ownership_ticket = AsyncMock()
    protocol_client.register_auth_ticket_with_cm = AsyncMock()
    protocol_client.close = AsyncMock()
    protocol_client.wait_closed = AsyncMock()
    return protocol_client


@pytest.fixture
def friends_cache():
    return MagicMock(FriendsCache)


@pytest.fixture
def games_cache():
    return MagicMock(GamesCache)


@pytest.fixture
def stats_cache():
    return MagicMock(StatsCache)


@pytest.fixture
def times_cache():
    return MagicMock(TimesCache)


@pytest.fixture
def translations_cache():
    return dict()


@pytest.fixture
def user_info_cache():
    return MagicMock(UserInfoCache)


@pytest.fixture
def local_machine_cache():
    return MagicMock()


@pytest.fixture
def ownership_ticket_cache():
    return MagicMock(OwnershipTicketCache)


@pytest.fixture
async def client(
    websocket_list,
    friends_cache,
    games_cache,
    translations_cache,
    stats_cache,
    times_cache,
    user_info_cache,
    local_machine_cache,
    ownership_ticket_cache,
):
    return WebSocketClient(
        websocket_list,
        MagicMock(ssl.SSLContext),
        friends_cache,
        games_cache,
        translations_cache,
        stats_cache,
        times_cache,
        user_info_cache,
        local_machine_cache,
        ownership_ticket_cache,
    )


@pytest.fixture
def patch_connect(mocker):
    def function(*args, **kwargs):
        return mocker.patch(
            "steam_network.websocket_client.websockets.connect", *args, **kwargs
        )

    return function


@pytest.mark.asyncio
async def test_connect_authenticate(
    client, patch_connect, protocol_client, websocket_list
):
    patch_connect(autospec=True)
    websocket_list.get.return_value = aiter(["wss://abc.com/websocket"])
    protocol_client.run.return_value = async_raise(AssertionError)
    credentials_mock = {"password": PASSWORD, "two_factor": TWO_FACTOR}
    plugin_queue_mock = AsyncMock()
    websocket_queue_mock = AsyncMock()
    websocket_queue_mock.get.return_value = credentials_mock
    error_queue_mock = AsyncMock()
    error_queue_mock.get.return_value = MagicMock()
    client.communication_queues = {
        "plugin": plugin_queue_mock,
        "websocket": websocket_queue_mock,
        "errors": error_queue_mock,
    }
    client._user_info_cache = MagicMock()
    client._user_info_cache.old_flow = False
    client._user_info_cache.token = False
    client._user_info_cache.account_username = ACCOUNT_NAME
    client._user_info_cache.two_step = None

    protocol_client.authenticate_password.return_value = async_return_value(
        UserActionRequired.NoActionRequired
    )
    with pytest.raises(AssertionError):
        await client.run()

    websocket_list.get.assert_called_once_with(0)
    protocol_client.run.assert_called_once_with()
    protocol_client.authenticate_password.assert_called_once_with(
        ACCOUNT_NAME, PASSWORD, TWO_FACTOR, ANY, ANY
    )


@pytest.mark.asyncio
async def test_websocket_close_reconnect(
    client, protocol_client, websocket_list, patch_connect
):
    patch_connect(autospec=True)
    websocket_list.get.side_effect = [
        aiter(["wss://abc.com/websocket"]),
        aiter(["wss://abc.com/websocket"]),
    ]
    protocol_client.run.side_effect = [
        async_raise(websockets.ConnectionClosedError(1002, ""), 10),
        async_raise(AssertionError),
    ]
    credentials_mock = {"password": PASSWORD, "two_factor": TWO_FACTOR}
    plugin_queue_mock = AsyncMock()
    websocket_queue_mock = AsyncMock()
    websocket_queue_mock.get.return_value = credentials_mock
    error_queue_mock = AsyncMock()
    error_queue_mock.get.return_value = MagicMock()
    client.communication_queues = {
        "plugin": plugin_queue_mock,
        "websocket": websocket_queue_mock,
        "errors": error_queue_mock,
    }

    protocol_client.close.return_value = async_return_value(None)
    protocol_client.wait_closed.return_value = async_return_value(None)
    protocol_client.authenticate_token = AsyncMock(return_value=MagicMock())

    client._user_info_cache = MagicMock()
    with pytest.raises(AssertionError):
        await client.run()

    assert websocket_list.get.call_count == 2
    assert protocol_client.authenticate_token.call_count == 2
    assert protocol_client.run.call_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("exception", [NetworkError()])
async def test_servers_cache_retry(
    client, protocol_client, websocket_list, mocker, exception, patch_connect
):
    patch_connect(autospec=True)
    websocket_list.get.side_effect = [
        aiter_raise(exception),
        aiter(["wss://abc.com/websocket"]),
    ]
    protocol_client.run.return_value = async_raise(AssertionError)
    sleep = mocker.patch(
        "steam_network.websocket_client.asyncio.sleep",
        side_effect=lambda x: async_return_value(None),
    )
    client._authenticate = AsyncMock()

    with pytest.raises(AssertionError):
        await client.run()
    assert websocket_list.get.call_count == 2
    sleep.assert_any_call(RECONNECT_INTERVAL_SECONDS)


@pytest.mark.asyncio
async def test_servers_cache_failure(client, protocol_client, websocket_list):
    websocket_list.get.return_value = aiter_raise(AccessDenied())
    with pytest.raises(AccessDenied):
        await client.run()
    websocket_list.get.assert_called_once_with(0)
    protocol_client.authenticate.assert_not_called()
    protocol_client.run.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exception",
    [
        asyncio.TimeoutError(),
        IOError(),
        websockets.InvalidURI("wss://websocket_1"),
        websockets.InvalidHandshake(),
    ],
)
async def test_connect_error(
    client, protocol_client, websocket_list, exception, patch_connect
):
    websocket_list.get.return_value = aiter(["wss://websocket_1", "wss://websocket_2"])
    connect = patch_connect(
        side_effect=[async_raise(exception), async_return_value(MagicMock())]
    )
    protocol_client.run.return_value = async_raise(AssertionError)
    client._authenticate = AsyncMock()
    with pytest.raises(AssertionError):
        await client.run()
    connect.assert_has_calls(
        [
            call("wss://websocket_1", max_size=ANY, ssl=ANY),
            call("wss://websocket_2", max_size=ANY, ssl=ANY),
        ]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exception",
    [
        asyncio.TimeoutError(),
        IOError(),
        websockets.InvalidURI("wss://websocket_1"),
        websockets.InvalidHandshake(),
    ],
)
async def test_connect_error_all_servers(
    client, protocol_client, websocket_list, mocker, exception, patch_connect
):
    websocket_list.get.side_effect = [
        aiter(["wss://websocket_1"]),
        aiter(["wss://websocket_1"]),
    ]
    connect = patch_connect(
        side_effect=[async_raise(exception), async_return_value(AsyncMock())],
    )
    sleep = mocker.patch(
        "steam_network.websocket_client.asyncio.sleep",
        side_effect=lambda x: async_return_value(None),
    )
    protocol_client.run.return_value = async_raise(AssertionError)
    client._authenticate = AsyncMock()
    with pytest.raises(AssertionError):
        await client.run()
    connect.assert_has_calls(
        [
            call("wss://websocket_1", max_size=ANY, ssl=ANY),
            call("wss://websocket_1", max_size=ANY, ssl=ANY),
        ]
    )
    sleep.assert_any_call(RECONNECT_INTERVAL_SECONDS)
    assert websocket_list.get.call_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("exception", [InvalidCredentials, AccessDenied])
async def test_auth_lost_handler(
    client,
    protocol_client,
    patch_connect,
    websocket_list,
    exception,
):
    client.authentication_lost_handler = Mock()
    patch_connect(autospec=True)
    websocket_list.get.return_value = aiter([Mock()])
    protocol_client.authenticate_token.return_value = async_return_value("ok")
    protocol_client.run.return_value = async_raise(
        AssertionError, loop_iterations_delay=10
    )

    mocked_steam_auth_lost = asyncio.Future()
    mocked_steam_auth_lost.set_exception(exception)
    await client.run(lambda: mocked_steam_auth_lost)

    client.authentication_lost_handler.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exception", [BackendNotAvailable(), BackendError(), BackendTimeout()]
)
async def test_handling_backend_not_available(
    client, protocol_client, websocket_list, exception, patch_connect
):
    """
    Usecase: eg. when receiving `ERestult.TryWithDifferentCM` or `EResult.ServiceUnavailable` from LogonResponse
    """
    unavailable_socket = "wss://cm1-lax1.cm.steampowered.com:27036"
    next_socket = "wss:/cm2-ord1.cm.steampowered.com:27010"
    websocket_list.get.return_value = aiter(
        [
            unavailable_socket,
            next_socket,
        ]
    )
    connect = patch_connect(
        side_effect=lambda *args, **kwargs: async_return_value(AsyncMock()),
    )
    protocol_client.authenticate_token.side_effect = [
        async_raise(exception),
        async_return_value(MagicMock(), loop_iterations_delay=5),
    ]
    # breaks from infinite loop after job is done before authentication task
    protocol_client.run.side_effect = lambda: async_return_value(
        None, loop_iterations_delay=2
    )

    await client.run()

    blacklisting_timeout = 300
    websocket_list.add_server_to_ignored.assert_called_once_with(
        unavailable_socket, timeout_sec=blacklisting_timeout
    )
    connect.assert_has_calls(
        [
            call(f"{unavailable_socket}", max_size=ANY, ssl=ANY),
            call(f"{next_socket}", max_size=ANY, ssl=ANY),
        ]
    )
