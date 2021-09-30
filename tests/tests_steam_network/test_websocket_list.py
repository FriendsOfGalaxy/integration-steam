from unittest.mock import Mock

import pytest
from galaxy.unittest.mock import AsyncMock

from steam_network.websocket_list import WebSocketList
from steam_network.steam_http_client import SteamHttpClient


@pytest.fixture
def current_time(mocker):
    return mocker.patch('steam_network.websocket_list.current_time')


@pytest.fixture
def backend_client():
    mock = Mock(SteamHttpClient)
    mock.get_servers = AsyncMock()
    return mock


@pytest.mark.asyncio
async def test_get_returns_sockets_received_from_backend_client(backend_client):
    cell_id = 0
    address_1 = "cm2-waw1.cm.teststeam.com:27039"
    address_2 = "cm3-waw3.cm.teststeam.com:27033"
    backend_client.get_servers.return_value = [address_1, address_2]
    websocket_list = WebSocketList(backend_client)

    servers = []
    async for i in websocket_list.get(cell_id):
        servers.append(i)

    assert servers == [f"wss://{address_1}/cmsocket/", f"wss://{address_2}/cmsocket/"]


@pytest.mark.asyncio
async def test_get_queries_list_with_given_cell_id(backend_client):
    cell_id = 1
    address = "cm2-waw1.cm.teststeam.com:27039"
    backend_client.get_servers.return_value = [address]
    websocket_list = WebSocketList(backend_client)

    async for i in websocket_list.get(cell_id):
        pass

    backend_client.get_servers.assert_called_once_with(cell_id)


@pytest.mark.asyncio
async def test_blacklisting_cm(backend_client):
    cell_id = 0
    backend_client.get_servers.return_value = [
        "cm1-waw1.cm.teststeam.com:27039",
        "cm1-fra1.cm.teststeam.com:24444",
        "cm3-waw3.cm.teststeam.com:27033",
        "cm1-waw1.cm.teststeam.com:27039",
        "cm1-fra1.cm.teststeam.com:24151",
        "cm1-ord2.cm.teststeam.com:273",
    ]
    blacklisted_addrs = [
        "cm1-waw1.cm.teststeam.com",
        "cm1-fra1.cm.teststeam.com",
    ]
    some_port, some_timeout = "27888", 100
    websocket_list = WebSocketList(backend_client)
    for bad_host in blacklisted_addrs:
        websocket_list.add_server_to_ignored(f"wss://{bad_host}:{some_port}", some_timeout)

    async for s in websocket_list.get(cell_id):
        for bad_host in blacklisted_addrs:
            assert bad_host not in s


@pytest.mark.asyncio
async def test_blacklist_timeout(backend_client, current_time):
    cell_id = 0
    backend_client.get_servers.return_value = [
        "cm1-waw1.cm.teststeam.com:27039",
    ]
    websocket_list = WebSocketList(backend_client)

    now, timeout = 123456780, 3
    current_time.return_value = now
    websocket_list.add_server_to_ignored("wss://cm1-waw1.cm.teststeam.com:1111", timeout)
    current_time.return_value = now + timeout + 1

    async for s in websocket_list.get(cell_id):
        assert "cm1-waw1.cm.teststeam.com" in s
        break
    else:
        pytest.fail('given socket was ignored despite reaching timeout')
    