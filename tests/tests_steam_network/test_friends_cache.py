from unittest.mock import MagicMock

import pytest

from tests.async_mock import AsyncMock
from steam_network.protocol.consts import EPersonaState
from steam_network.protocol.steam_types import ProtoUserInfo
from steam_network.friends_cache import FriendsCache


@pytest.fixture
def cache():
    return FriendsCache()


@pytest.fixture
def added_handler(cache):
    mock = MagicMock()
    cache.added_handler = mock
    return mock


@pytest.fixture
def removed_handler(cache):
    mock = MagicMock()
    cache.removed_handler = mock
    return mock


@pytest.fixture
def updated_handler(cache):
    mock = MagicMock()
    cache.updated_handler = AsyncMock
    return mock


def test_empty(cache):
    assert not cache.ready
    assert list(cache) == []


def test_add_user(cache, added_handler):
    user_id = 1423
    cache.add(user_id)
    assert not cache.ready
    assert user_id in cache
    assert list(cache) == [(user_id, ProtoUserInfo())]
    added_handler.assert_not_called()


@pytest.mark.asyncio
async def test_update_user_not_ready(cache, added_handler, updated_handler):
    user_id = 1423
    user_info = ProtoUserInfo("Jan")
    cache.add(user_id)
    await cache.update(user_id, user_info)
    assert not cache.ready
    assert list(cache) == [(user_id, user_info)]
    added_handler.assert_not_called()
    updated_handler.assert_not_called()


@pytest.mark.asyncio
async def test_update_user_ready(cache, added_handler, updated_handler):
    user_id = 1423
    expected_user_info = ProtoUserInfo(name="Jan", state=EPersonaState.Offline)
    cache.add(user_id)
    await cache.update(user_id, ProtoUserInfo(name="Jan"))
    await cache.update(user_id, ProtoUserInfo(state=EPersonaState.Offline))
    assert cache.ready
    assert list(cache) == [(user_id, expected_user_info)]
    added_handler.assert_called_with(user_id, expected_user_info)
    updated_handler.assert_not_called()


@pytest.mark.asyncio
async def test_update_user_all_data(cache, added_handler, updated_handler):
    user_id = 1423
    user_info = ProtoUserInfo(name="Jan", state=EPersonaState.Offline)
    cache.add(user_id)
    await cache.update(user_id, user_info)
    assert cache.ready
    assert list(cache) == [(user_id, user_info)]
    added_handler.assert_called_with(user_id, user_info)
    updated_handler.assert_not_called()


def test_remove_not_ready_user(cache, removed_handler):
    user_id = 1423
    cache.add(user_id)
    cache.remove(user_id)
    assert cache.ready
    assert list(cache) == []
    removed_handler.assert_not_called()


@pytest.mark.asyncio
async def test_remove_ready_user(cache, removed_handler):
    user_id = 1423
    user_info = ProtoUserInfo(name="Jan", state=EPersonaState.Offline)
    cache.add(user_id)
    await cache.update(user_id, user_info)
    cache.remove(user_id)
    assert list(cache) == []
    removed_handler.assert_called_once_with(user_id)


def test_reset_empty(cache):
    cache.reset([])
    assert cache.ready
    assert list(cache) == []


@pytest.mark.asyncio
async def test_reset_mixed(cache, removed_handler):
    cache.add(15)
    await cache.update(15, ProtoUserInfo(name="Jan", state=EPersonaState.Offline))

    cache.add(17)
    await cache.update(17, ProtoUserInfo(name="Ula", state=EPersonaState.Offline))

    cache.reset([17, 29])
    removed_handler.assert_called_once_with(15)
    assert not cache.ready
