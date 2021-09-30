import asyncio

from unittest.mock import MagicMock, ANY
from typing import NamedTuple

import pytest

from galaxy.unittest.mock import async_return_value, AsyncMock, skip_loop
from galaxy.api.errors import AccessDenied, Banned

from steam_network.protocol.protobuf_client import SteamLicense
from steam_network.protocol.consts import EFriendRelationship, STEAM_CLIENT_APP_ID, EResult
from steam_network.protocol_client import ProtocolClient
from steam_network.protocol.types import ProtoUserInfo


class ProtoResponse(NamedTuple):
    package_id: int


STEAM_ID = 71231321
MINIPROFILE_ID = 123
ACCOUNT_NAME = "john"
TOKEN = "TOKEN"


@pytest.fixture
def protobuf_client(mocker):
    mock = mocker.patch("steam_network.protocol_client.ProtobufClient")
    return mock.return_value

@pytest.fixture()
def friends_cache():
    return MagicMock()

@pytest.fixture()
def games_cache():
    return MagicMock()

@pytest.fixture()
def stats_cache():
    return MagicMock()

@pytest.fixture()
def user_info_cache():
    return AsyncMock()

@pytest.fixture()
def local_machine_cache():
    return MagicMock()

@pytest.fixture()
def times_cache():
    return MagicMock()

@pytest.fixture()
def used_server_cellid():
    return MagicMock()

@pytest.fixture()
def ownership_ticket_cache():
    return MagicMock()

@pytest.fixture()
def translations_cache():
    return dict()

@pytest.fixture
async def client(protobuf_client, friends_cache, games_cache, translations_cache, stats_cache, times_cache, user_info_cache, local_machine_cache, ownership_ticket_cache, used_server_cellid):
    return ProtocolClient(protobuf_client, friends_cache, games_cache, translations_cache, stats_cache, times_cache, user_info_cache, local_machine_cache, ownership_ticket_cache, used_server_cellid)


@pytest.mark.asyncio
async def test_close(client, protobuf_client):
    protobuf_client.close.return_value = async_return_value(None)
    await client.close(True)
    protobuf_client.close.assert_called_once_with(True)


@pytest.mark.asyncio
async def test_authenticate_success(client, protobuf_client):
    protobuf_client.log_on_token.return_value = async_return_value(None)
    protobuf_client.account_info_retrieved.wait.return_value = async_return_value(True, loop_iterations_delay=1)
    auth_task = asyncio.create_task(client.authenticate_token(STEAM_ID, ACCOUNT_NAME, TOKEN, None))
    await skip_loop()
    await protobuf_client.log_on_handler(EResult.OK)
    await auth_task
    assert protobuf_client.steam_id == STEAM_ID
    protobuf_client.log_on_token.assert_called_once_with(ACCOUNT_NAME, TOKEN, ANY, ANY, ANY, ANY)


@pytest.mark.asyncio
async def test_authenticate_failure(client, protobuf_client):
    auth_lost_handler = MagicMock()
    protobuf_client.log_on_token.return_value = async_return_value(None)
    auth_task = asyncio.create_task(client.authenticate_token(STEAM_ID, ACCOUNT_NAME, TOKEN, auth_lost_handler))
    await skip_loop()
    await protobuf_client.log_on_handler(EResult.AccessDenied)
    with pytest.raises(AccessDenied):
        await auth_task
    auth_lost_handler.assert_not_called()


@pytest.mark.asyncio
async def test_log_out(client, protobuf_client):
    auth_lost_handler = MagicMock(return_value=async_return_value(None))
    protobuf_client.log_on_token.return_value = async_return_value(None)
    protobuf_client.account_info_retrieved.wait.return_value = async_return_value(True, loop_iterations_delay=1)
    auth_task = asyncio.create_task(client.authenticate_token(STEAM_ID, ACCOUNT_NAME, TOKEN, auth_lost_handler))
    await skip_loop()
    await protobuf_client.log_on_handler(EResult.OK)
    await auth_task
    await protobuf_client.log_off_handler(EResult.Banned)
    auth_lost_handler.assert_called_with(Banned({"result": EResult.Banned}))


@pytest.mark.asyncio
async def test_relationship_initial(client, protobuf_client, friends_cache):
    friends = {
        15: EFriendRelationship.Friend,
        56: EFriendRelationship.Friend
    }

    protobuf_client.set_persona_state.return_value = async_return_value(None)
    protobuf_client.get_friends_statuses.return_value = async_return_value(None)
    protobuf_client.get_user_infos.return_value = async_return_value(None)
    await protobuf_client.relationship_handler(False, friends)
    friends_cache.reset.assert_called_once_with([15, 56])
    protobuf_client.get_friends_statuses.assert_called_once_with()
    protobuf_client.get_user_infos.assert_called_once_with([15, 56], ANY)


@pytest.mark.asyncio
async def test_relationship_update(client, protobuf_client, friends_cache):
    friends = {
        15: EFriendRelationship.Friend,
        56: EFriendRelationship.None_
    }
    protobuf_client.get_friends_statuses.return_value = async_return_value(None)
    protobuf_client.get_user_infos.return_value = async_return_value(None)
    await protobuf_client.relationship_handler(True, friends)
    friends_cache.add.assert_called_once_with(15)
    friends_cache.remove.assert_called_once_with(56)
    protobuf_client.get_friends_statuses.assert_called_once_with()
    protobuf_client.get_user_infos.assert_called_once_with([15], ANY)


@pytest.mark.asyncio
async def test_user_info(client, protobuf_client, friends_cache):
    user_id = 15
    user_info = ProtoUserInfo("Ola")
    friends_cache.update = AsyncMock()
    await protobuf_client.user_info_handler(user_id, user_info)
    friends_cache.update.assert_called_once_with(user_id, user_info)


@pytest.mark.asyncio
async def test_license_import(client):
    licenses_to_check = [SteamLicense(ProtoResponse(123), False),
                        SteamLicense(ProtoResponse(321), True)]
    client._protobuf_client.get_packages_info = AsyncMock()
    await client._license_import_handler(licenses_to_check)

    client._games_cache.reset_storing_map.assert_called_once()
    client._protobuf_client.get_packages_info.assert_called_once_with(licenses_to_check)


@pytest.mark.asyncio
async def test_register_cm_token(client, ownership_ticket_cache):
    ticket = 'ticket_mock'
    await client._app_ownership_ticket_handler(STEAM_CLIENT_APP_ID, ticket)
    assert ownership_ticket_cache.ticket == ticket
