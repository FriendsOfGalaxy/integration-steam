import asyncio
from unittest.mock import MagicMock, ANY, Mock
from typing import NamedTuple, List
import json

import pytest

from galaxy.unittest.mock import async_return_value, AsyncMock, skip_loop
from galaxy.api.errors import AccessDenied, Banned, BackendNotAvailable

from steam_network.protocol.protobuf_client import SteamLicense
from steam_network.protocol.consts import EFriendRelationship, STEAM_CLIENT_APP_ID, EResult
from steam_network.protocol_client import ProtocolClient
from steam_network.protocol.steam_types import ProtoUserInfo


class ProtoResponse(NamedTuple):
    package_id: int


class AchievementBlock(NamedTuple):
    """Mocked element of steammessages_clientserver_pb2.Achievement_Blocks"""
    achievement_id: int
    unlock_time: List[int]


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
async def test_protocol_connection_with_authentication(
    client,
    protobuf_client,
):
    protobuf_client.log_on_token.return_value = async_return_value(None)
    protobuf_client.run = AsyncMock()
    protobuf_client.account_info_retrieved.wait.return_value = async_return_value(True, loop_iterations_delay=1)

    auth_task = asyncio.create_task(client.authenticate_token(STEAM_ID, ACCOUNT_NAME, TOKEN, None))
    run_task = asyncio.create_task(client.run())
    await skip_loop()
    await protobuf_client.log_on_handler(EResult.OK)
    await auth_task
    await run_task

    assert protobuf_client.steam_id == STEAM_ID
    protobuf_client.log_on_token.assert_called_once_with(ACCOUNT_NAME, TOKEN, ANY, ANY, ANY, ANY)


@pytest.mark.asyncio
async def test_protocol_connection_failure_with_backend_not_available__eresult48(client, protobuf_client):
    protobuf_client.run.return_value = asyncio.create_task(protobuf_client.log_on_handler(EResult.TryAnotherCM))

    with pytest.raises(BackendNotAvailable):
        await client.run()


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


@pytest.mark.parametrize('bit_schema', [
    pytest.param("""
        {
            "name":"ENTER_ESOPHAGUS",
            "display":{
                "name":{
                    "english":"Get Eaten",
                    "token":"NEW_ACHIEVEMENT_1_0_NAME"
                },
                "desc":{
                    "english":"Get eaten by the bird.",
                    "token":"NEW_ACHIEVEMENT_1_0_DESC"
                },
                "hidden":"0"
            },
            "bit":0
        }""",
        id="name as a dict with `english` key"),
    pytest.param("""
        {
            "name":"ENTER_ESOPHAGUS",
            "display":{
                "name":"Get Eaten",
                "desc":"Get eaten by the bird.",
                "hidden":"0"
            },
            "bit":0
        }""",
        id="name as a string"
    ),
])
@pytest.mark.asyncio
async def test_stats_displayed_name(client, stats_cache, bit_schema):
    """
    It happens that achievement schema has name in simple or rich form (with multilanguage support).
    Parser should get what is available with preference for english.
    """
    stats = Mock()
    game_id, achievement_id = "1072390", 1
    schema = {
        game_id: {
            "stats": {
                str(achievement_id): {
                    "bits": {
                        "0": json.loads(bit_schema)
                    },
                    "type": "4",
                    "id": "1"
                }
            },
        "version": "3"
        }
    }
    achievement_blocks = [AchievementBlock(achievement_id=achievement_id, unlock_time=[1511111111])]

    client._stats_handler(game_id, stats, achievement_blocks, schema)
    stats_cache.update_stats.assert_called_once_with(game_id, stats, [
        {
            'id': 0,
            'unlock_time': 1511111111,
            'name': "Get Eaten"
        },
    ])


@pytest.mark.asyncio
async def test_stats_handler_2_achievements_unlocked(client, stats_cache):
    stats = Mock()
    game_id = "1072390"
    schema = json.loads("""
        {"1072390": {"stats": {"1": {"bits": {
            "0": {"name": "ENTER_ESOPHAGUS", "display": {"name": {"english": "Get Eaten", "token": "NEW_ACHIEVEMENT_1_0_NAME"}, "desc": {"english": "Get eaten by the bird.", "token": "NEW_ACHIEVEMENT_1_0_DESC"}, "hidden": "0", "icon_gray": "e70189b4cc55d4283357b005b12852ce67a08c0e.jpg", "icon": "a2da39ea0d23962316df4c2ca7983eeb2e0c9776.jpg"}, "bit": 0},
            "1": {"name": "ENTER_STOMACH", "display": {"name": {"english": "The Fabulous Stomach", "token": "NEW_ACHIEVEMENT_1_1_NAME"}, "desc": {"english": "Reach the stomach of the bird", "token": "NEW_ACHIEVEMENT_1_1_DESC"}, "hidden": "0", "icon_gray": "e70189b4cc55d4283357b005b12852ce67a08c0e.jpg", "icon": "7bc816d475da1a0c55a8ab5dc24731739cbc6d2a.jpg"}, "bit": 1},
            "2": {"name": "ENTER_CITY_1", "display": {"name": {"english": "Peculiar Dwellings", "token": "NEW_ACHIEVEMENT_1_2_NAME"}, "desc": {"english": "Reach the stomach city", "token": "NEW_ACHIEVEMENT_1_2_DESC"}, "hidden": "0", "icon_gray": "e70189b4cc55d4283357b005b12852ce67a08c0e.jpg", "icon": "d2da576dc33e4d3e629d3fe902de3b9f79f484bd.jpg"}, "bit": 2},
            "3": {"name": "ENTER_CITY_2", "display": {"name": {"english": "Construction and Destruction", "token": "NEW_ACHIEVEMENT_1_3_NAME"}, "desc": {"english": "Reach the stomach city's upper zone", "token": "NEW_ACHIEVEMENT_1_3_DESC"}, "hidden": "0", "icon_gray": "e70189b4cc55d4283357b005b12852ce67a08c0e.jpg", "icon": "b27fc3d065711e75090e4d6c6d5d668efe4bdccf.jpg"}, "bit": 3},
            "4": {"name": "ENTER_STOMACH_BOSS", "display": {"name": {"english": "The Floor is Acid", "token": "NEW_ACHIEVEMENT_1_4_NAME"}, "desc": {"english": "Reach the Acid Ocean", "token": "NEW_ACHIEVEMENT_1_4_DESC"}, "hidden": "0", "icon_gray": "e70189b4cc55d4283357b005b12852ce67a08c0e.jpg", "icon": "5f752e72e9f27681fa5d81d239049f4282f375c9.jpg"}, "bit": 4}, "5": {"name": "ENTER_SMALL_INT", "display": {"name": {"english": "Twists and Turns", "token": "NEW_ACHIEVEMENT_1_5_NAME"}, "desc": {"english": "Reach the small intestines", "token": "NEW_ACHIEVEMENT_1_5_DESC"}, "hidden": "0", "icon_gray": "e70189b4cc55d4283357b005b12852ce67a08c0e.jpg", "icon": "e85fbddbe4114dacca5bd6afc62157aff2c56164.jpg"}, "bit": 5}, "6": {"name": "ENTER_LARGE_INT", "display": {"name": {"english": "Junk and Rubbish", "token": "NEW_ACHIEVEMENT_1_6_NAME"}, "desc": {"english": "Reach the large intestines", "token": "NEW_ACHIEVEMENT_1_6_DESC"}, "hidden": "0", "icon_gray": "e70189b4cc55d4283357b005b12852ce67a08c0e.jpg", "icon": "252eefd9b507fbc6150ce45be531d8e0386a3026.jpg"}, "bit": 6}, "7": {"name": "ENTER_COLON", "display": {"name": {"english": "Armed Insects", "token": "NEW_ACHIEVEMENT_1_7_NAME"}, "desc": {"english": "Reach the colon", "token": "NEW_ACHIEVEMENT_1_7_DESC"}, "hidden": "0", "icon_gray": "e70189b4cc55d4283357b005b12852ce67a08c0e.jpg", "icon": "469131f0551d98ad5eb85f3ff20b947ad56dcc08.jpg"}, "bit": 7}, "8": {"name": "ENTER_MISSILES", "display": {"name": {"english": "Big ol' Bombs", "token": "NEW_ACHIEVEMENT_1_8_NAME"}, "desc": {"english": "Reach the Missile Chamber", "token": "NEW_ACHIEVEMENT_1_8_DESC"}, "hidden": "0", "icon_gray": "e70189b4cc55d4283357b005b12852ce67a08c0e.jpg", "icon": "2acdc68a10cb37c20e76016ba1cc66971158f171.jpg"}, "bit": 8}, "9": {"name": "END_LAUNCH", "display": {"name": {"english": "Going Down with the Ship", "token": "NEW_ACHIEVEMENT_1_9_NAME"}, "desc": {"english": "Obtain the launch ending", "token": "NEW_ACHIEVEMENT_1_9_DESC"}, "hidden": "0", "icon_gray": "e70189b4cc55d4283357b005b12852ce67a08c0e.jpg", "icon": "1b3d984339f44c7cbc6708e2bc1bc6473afb77c8.jpg"}, "bit": 9}, "10": {"name": "END_ESCAPE", "display": {"name": {"english": "Lose-Lose", "token": "NEW_ACHIEVEMENT_1_10_NAME"}, "desc": {"english": "Obtain the escape ending", "token": "NEW_ACHIEVEMENT_1_10_DESC"}, "hidden": "0", "icon_gray": "e70189b4cc55d4283357b005b12852ce67a08c0e.jpg", "icon": "93906e0dbbf9f6c91e7072ca0e13ce5a7c88bf5b.jpg"}, "bit": 10}, "11": {"name": "END_LAUNCH_ESCAPE", "display": {"name": {"english": "The Hatless One", "token": "NEW_ACHIEVEMENT_1_11_NAME"}, "desc": {"english": "Obtain the launch and escape ending", "token": "NEW_ACHIEVEMENT_1_11_DESC"}, "hidden": "0", "icon_gray": "e70189b4cc55d4283357b005b12852ce67a08c0e.jpg", "icon": "3791ff26dfd7da86e2427ed48d5455992253f9a6.jpg"}, "bit": 11}, "12": {"name": "SECRET_1", "display": {"name": {"english": "The First of the Hidden", "token": "NEW_ACHIEVEMENT_1_12_NAME"}, "desc": {"english": "Discover the Skull of the First", "token": "NEW_ACHIEVEMENT_1_12_DESC"}, "hidden": "0", "icon_gray": "e70189b4cc55d4283357b005b12852ce67a08c0e.jpg", "icon": "6daafb85f2c67e17a8403cceedda1a69f730ac05.jpg"}, "bit": 12}, "13": {"name": "SECRET_2", "display": {"name": {"english": "The Second of the Hidden", "token": "NEW_ACHIEVEMENT_1_13_NAME"}, "desc": {"english": "Discover the Skull of the Second", "token": "NEW_ACHIEVEMENT_1_13_DESC"}, "hidden": "0", "icon_gray": "e70189b4cc55d4283357b005b12852ce67a08c0e.jpg", "icon": "0fbce3210d35b6c48254f1b1f08d57682f00c0d6.jpg"}, "bit": 13}, "14": {"name": "SECRET_3", "display": {"name": {"english": "The Third of the Hidden", "token": "NEW_ACHIEVEMENT_1_14_NAME"}, "desc": {"english": "Discover the Skull of the Third", "token": "NEW_ACHIEVEMENT_1_14_DESC"}, "hidden": "0", "icon_gray": "e70189b4cc55d4283357b005b12852ce67a08c0e.jpg", "icon": "05601e4c89c1abe5e22bae31322b4bb950153294.jpg"}, "bit": 14}, "15": {"name": "SECRET_4", "display": {"name": {"english": "The Fourth of the Hidden", "token": "NEW_ACHIEVEMENT_1_15_NAME"}, "desc": {"english": "Discover the Skull of the Fourth", "token": "NEW_ACHIEVEMENT_1_15_DESC"}, "hidden": "0", "icon_gray": "e70189b4cc55d4283357b005b12852ce67a08c0e.jpg", "icon": "81cc206d8c2eecf2b1eb1d844e16eb5183aacd4b.jpg"}, "bit": 15}, "16": {"name": "SECRET_5", "display": {"name": {"english": "The Fifth of the Hidden", "token": "NEW_ACHIEVEMENT_1_16_NAME"}, "desc": {"english": "Discover the Skull of the Fifth", "token": "NEW_ACHIEVEMENT_1_16_DESC"}, "hidden": "0", "icon_gray": "e70189b4cc55d4283357b005b12852ce67a08c0e.jpg", "icon": "5b67c5e88496f0d29556e8effb07fc5465d86678.jpg"}, "bit": 16}, "17": {"name": "SECRET_6", "display": {"name": {"english": "The Sixth of the Hidden", "token": "NEW_ACHIEVEMENT_1_17_NAME"}, "desc": {"english": "Discover the Skull of the Sixth", "token": "NEW_ACHIEVEMENT_1_17_DESC"}, "hidden": "0", "icon_gray": "e70189b4cc55d4283357b005b12852ce67a08c0e.jpg", "icon": "a39379829c3e426591e6bc28d1ead946d3f076fa.jpg"}, "bit": 17}, "18": {"name": "SECRET_7", "display": {"name": {"english": "The Seventh of the Hidden", "token": "NEW_ACHIEVEMENT_1_18_NAME"}, "desc": {"english": "Discover the Skull of the Seventh", "token": "NEW_ACHIEVEMENT_1_18_DESC"}, "hidden": "0", "icon_gray": "e70189b4cc55d4283357b005b12852ce67a08c0e.jpg", "icon": "96c61a45f30688664846bd9c250beca2a672ee61.jpg"}, "bit": 18}, "19": {"name": "SECRET_8", "display": {"name": {"english": "The Eighth of the Hidden", "token": "NEW_ACHIEVEMENT_1_19_NAME"}, "desc": {"english": "Discover the Skull of the Eighth", "token": "NEW_ACHIEVEMENT_1_19_DESC"}, "hidden": "0", "icon_gray": "e70189b4cc55d4283357b005b12852ce67a08c0e.jpg", "icon": "6e9853f76b930e8ba0ecbcf1f4904bd210b0b6c9.jpg"}, "bit": 19}, "20": {"name": "SECRET_9", "display": {"name": {"english": "The Ninth of the Hidden", "token": "NEW_ACHIEVEMENT_1_20_NAME"}, "desc": {"english": "Discover the Skull of the Ninth", "token": "NEW_ACHIEVEMENT_1_20_DESC"}, "hidden": "0", "icon_gray": "e70189b4cc55d4283357b005b12852ce67a08c0e.jpg", "icon": "1618599f87f64ce0bb1fcc723e4ee5cd3860553b.jpg"}, "bit": 20}, "21": {"name": "BLESSING", "display": {"name": {"english": "Blessed", "token": "NEW_ACHIEVEMENT_1_21_NAME"}, "desc": {"english": "Receive the Blessing of the Nine", "token": "NEW_ACHIEVEMENT_1_21_DESC"}, "hidden": "1", "icon_gray": "e70189b4cc55d4283357b005b12852ce67a08c0e.jpg", "icon": "27639a4385d56b91d8a4bbb99b86417d01bf142f.jpg"}, "bit": 21}},
             "type": "4", "id": "1"}}, "version": "3"}}
    """)
    achievement_blocks = [
        AchievementBlock(achievement_id=1, unlock_time=[
            0, 0, 1569838829, 1569839257, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        ])
    ]
    client._stats_handler(game_id, stats, achievement_blocks, schema)
    stats_cache.update_stats.assert_called_once_with(game_id, stats, [
        {
            'id': 2,
            'unlock_time': 1569838829,
            'name': "Peculiar Dwellings"
        },
        {
            "id": 3,
            "unlock_time": 1569839257,
            'name': "Construction and Destruction"
        }
    ])


@pytest.mark.asyncio
async def test_stats_handler_for_not_matching_schema(client, stats_cache):
    """
    It happens that unlocked achievements does not conform schema.
    Parser should ommit those unknown unlocked timestamps and go ahead.

    Probably caused by post-release achievements schema changes pushed by game devs.

    For example it happened in Train Simulator (the case from #114) that
    we received an item with achievement_id=3 that contains a block of timestamps (like for regular achievement bits),
    but in the schema stat of id=3 was an ordinary numerical (type=2) stat ("Night Rider Miles Driven").
    """
    stats = Mock()
    game_id = "24010"  # Train Simulator
    schema = json.loads("""
        {"24010": {"stats": {
        "1": { "type": "1", "name": "points",
            "display": { "name": "Total Points" }, "default": "0", "id": "1"},
        "2": { "type": "1", "name": "sce.84511f30-b03f-4262-a99f-5b7798473b05.Complete",
            "display": { "name": "Completed LB Intro" }, "id": "2"},
        "3": { "type": "2", "name": "sce.45d4e4b1-8ba8-4878-bb4c-4833e653fa5a.DistanceTravelled.Miles",
            "display": {"name": "Night Rider Miles Driven" }, "default": "0", "id": "3"},
        "4": { "bits": {
          "15": {"name": "222588_Hamburg Hanover: Short Journey Completed", "display": { "name": { "english": "Hamburg Hanover: Short Journey Completed", "token": "NEW_ACHIEVEMENT_4_15_NAME" }, "desc": { "english": "Complete the Career Scenario: An ICE Cool Morning", "token": "NEW_ACHIEVEMENT_4_15_DESC" }, "hidden": "0", "icon": "3a12ccb9f70de3ccb62fed676c9d5be965b5432a.jpg", "icon_gray": "71147139808fd0eb2a30cb82473cf3930d1e1c66.jpg" }, "progress": { "min_val": "0", "max_val": "1", "value": { "operation": "statvalue", "operand1": "sce.f77bf203-bf40-4c21-91bb-f5665e9e1001.Complete"}}, "bit": 15},
          "16": {"name": "222588_Hamburg Hanover: Top Shunter", "display": { "name": { "english": "Hamburg Hanover: Top Shunter", "token": "NEW_ACHIEVEMENT_4_16_NAME" }, "desc": { "english": "Complete the Career Scenario: Diesel Dock Duties", "token": "NEW_ACHIEVEMENT_4_16_DESC" }, "hidden": "0", "icon": "b51535f66e143a0b390cc37c98396a9df90ee4b5.jpg", "icon_gray": "71147139808fd0eb2a30cb82473cf3930d1e1c66.jpg" }, "progress": { "min_val": "0", "max_val": "1", "value": { "operation": "statvalue", "operand1": "sce.85128c1b-84cb-428a-b683-a7113d398f0c.Complete" } }, "bit": 16},
          "type": "4",
          "id": "4"
        }}}}}
    """)
    achievement_blocks = [
        # block containing unlock timestamps for id=3 that matches with numerical stat (what does not makes sense)
        AchievementBlock(achievement_id=3, unlock_time=[
            0, 1569838829, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        ]),
        # block containing unlock timestamps for id=4 that matches with a valid achievements schema
        AchievementBlock(achievement_id=4, unlock_time=[
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1569550456, 1569999999, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        ])
    ]
    client._stats_handler(game_id, stats, achievement_blocks, schema)
    stats_cache.update_stats.assert_called_once_with(game_id, stats, [
        { 
            "id": 3 * 32 + 15,
            "name": "Hamburg Hanover: Short Journey Completed",
            "unlock_time": 1569550456,
        },
        { 
            "id": 3 * 32 + 16,
            "name": "Hamburg Hanover: Top Shunter",
            "unlock_time": 1569999999,
        }
    ])
