import asyncio
from asyncio.futures import Future
import logging
import ssl
from contextlib import suppress
from typing import Callable, Optional

import websockets
from galaxy.api.errors import BackendNotAvailable, BackendTimeout, BackendError, InvalidCredentials, NetworkError, AccessDenied

from .websocket_list import WebSocketList
from .friends_cache import FriendsCache
from .games_cache import GamesCache
from .local_machine_cache import LocalMachineCache
from .ownership_ticket_cache import OwnershipTicketCache
from .protocol_client import ProtocolClient, UserActionRequired
from .stats_cache import StatsCache
from .times_cache import TimesCache
from .user_info_cache import UserInfoCache


logger = logging.getLogger(__name__)
# do not log low level events from websockets
logging.getLogger("websockets").setLevel(logging.WARNING)


RECONNECT_INTERVAL_SECONDS = 20
MAX_INCOMING_MESSAGE_SIZE = 2**24
BLACKLISTED_CM_EXPIRATION_SEC = 300


async def sleep(seconds: int):
    await asyncio.sleep(seconds)


def asyncio_future() -> Future:
    loop = asyncio.get_event_loop()
    return loop.create_future()


class WebSocketClient:
    def __init__(
        self,
        websocket_list: WebSocketList,
        ssl_context: ssl.SSLContext,
        friends_cache: FriendsCache,
        games_cache: GamesCache,
        translations_cache: dict,
        stats_cache: StatsCache,
        times_cache: TimesCache,
        user_info_cache: UserInfoCache,
        local_machine_cache: LocalMachineCache,
        ownership_ticket_cache: OwnershipTicketCache
    ):
        self._ssl_context = ssl_context
        self._websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._protocol_client: Optional[ProtocolClient] = None
        self._websocket_list = websocket_list

        self._friends_cache = friends_cache
        self._games_cache = games_cache
        self._translations_cache = translations_cache
        self._stats_cache = stats_cache
        self._user_info_cache = user_info_cache
        self._local_machine_cache = local_machine_cache
        self._steam_app_ownership_ticket_cache = ownership_ticket_cache
        self._times_cache = times_cache

        self.authentication_lost_handler: Optional[Callable] = None
        self.communication_queues = {'plugin': asyncio.Queue(), 'websocket': asyncio.Queue(), 'errors': asyncio.Queue()}
        self.used_server_cell_id: int = 0
        self._current_ws_address: Optional[str] = None

    async def run(self, create_future_factory: Callable[[], Future]=asyncio_future):
        while True:
            try:
                await self._ensure_connected()

                run_task = asyncio.create_task(self._protocol_client.run())
                auth_lost = create_future_factory()
                auth_task = asyncio.create_task(self._authenticate(auth_lost))
                pending = None
                try:
                    done, pending = await asyncio.wait({run_task, auth_task}, return_when=asyncio.FIRST_COMPLETED)
                    if auth_task in done:
                        await auth_task

                    done, pending = await asyncio.wait({run_task, auth_lost}, return_when=asyncio.FIRST_COMPLETED)
                    if auth_lost in done:
                        try:
                            await auth_lost
                        except (InvalidCredentials, AccessDenied) as e:
                            logger.warning(f"Auth lost by a reason: {repr(e)}")
                            if self.authentication_lost_handler:
                                self.authentication_lost_handler()
                            await self._close_socket()
                            await self._close_protocol_client()
                            run_task.cancel()
                            break

                    assert run_task in done
                    await run_task
                    break
                except Exception:
                    with suppress(asyncio.CancelledError):
                        if pending is not None:
                            for task in pending:
                                task.cancel()
                                await task
                    raise
            except asyncio.CancelledError as e:
                logger.warning(f"Websocket task cancelled {repr(e)}")
                raise
            except websockets.ConnectionClosedOK:
                logger.debug("Expected WebSocket disconnection")
            except websockets.ConnectionClosedError as error:
                logger.warning("WebSocket disconnected (%d: %s), reconnecting...", error.code, error.reason)
            except websockets.InvalidState as error:
                logger.warning("WebSocket is trying to connect...", error.code, error.reason)
            except (BackendNotAvailable, BackendTimeout, BackendError) as e:
                logger.warning(f"{repr(e)}. Trying with different CM...")
                self._websocket_list.add_server_to_ignored(self._current_ws_address, timeout_sec=BLACKLISTED_CM_EXPIRATION_SEC)
            except NetworkError:
                logger.exception(
                    "Failed to establish authenticated WebSocket connection, retrying after %d seconds",
                    RECONNECT_INTERVAL_SECONDS
                )
                await sleep(RECONNECT_INTERVAL_SECONDS)
                continue
            except Exception as e:
                logger.exception(f"Failed to establish authenticated WebSocket connection {repr(e)}")
                await self.communication_queues['errors'].put(e)
                raise

            await self._close_socket()
            await self._close_protocol_client()

    async def _close_socket(self):
        if self._websocket is not None:
            logger.info("Closing websocket")
            await self._websocket.close()
            await self._websocket.wait_closed()
            self._websocket = None

    async def _close_protocol_client(self):
        is_socket_connected = True if self._websocket else False
        if self._protocol_client is not None:
            logger.info("Closing protocol client")
            await self._protocol_client.close(is_socket_connected)
            await self._protocol_client.wait_closed()
            self._protocol_client = None

    async def close(self):
        is_socket_connected = True if self._websocket else False
        if self._protocol_client is not None:
            await self._protocol_client.close(is_socket_connected)
        if self._websocket is not None:
            await self._websocket.close()

    async def wait_closed(self):
        if self._protocol_client is not None:
            await self._protocol_client.wait_closed()
        if self._websocket is not None:
            await self._websocket.wait_closed()

    async def get_friends(self):
        await self._friends_cache.wait_ready()
        return [str(user_id) for user_id in self._friends_cache.get_keys()]

    async def get_friends_nicknames(self):
        await self._friends_cache.wait_nicknames_ready()
        return self._friends_cache.get_nicknames()

    async def get_friends_info(self, users):
        await self._friends_cache.wait_ready()
        result = {}
        for user_id in users:
            int_user_id = int(user_id)
            user_info = self._friends_cache.get(int_user_id)
            if user_info is not None:
                result[user_id] = user_info
        return result

    async def refresh_game_stats(self, game_ids):
        self._stats_cache.start_game_stats_import(game_ids)
        await self._protocol_client.import_game_stats(game_ids)

    async def refresh_game_times(self):
        self._times_cache.start_game_times_import()
        await self._protocol_client.import_game_times()

    async def retrieve_collections(self):
        return await self._protocol_client.retrieve_collections()

    async def _ensure_connected(self):
        if self._protocol_client is not None:
            return  # already connected

        while True:
            async for ws_address in self._websocket_list.get(self.used_server_cell_id):
                self._current_ws_address = ws_address
                try:
                    self._websocket = await asyncio.wait_for(websockets.connect(ws_address, ssl=self._ssl_context, max_size=MAX_INCOMING_MESSAGE_SIZE), 5)
                    self._protocol_client = ProtocolClient(self._websocket, self._friends_cache, self._games_cache, self._translations_cache, self._stats_cache, self._times_cache, self._user_info_cache, self._local_machine_cache, self._steam_app_ownership_ticket_cache, self.used_server_cell_id)
                    logger.info(f'Connected to Steam on CM {ws_address} on cell_id {self.used_server_cell_id}')
                    return
                except (asyncio.TimeoutError, OSError, websockets.InvalidURI, websockets.InvalidHandshake):
                    self._websocket_list.add_server_to_ignored(self._current_ws_address, timeout_sec=BLACKLISTED_CM_EXPIRATION_SEC)
                    continue

            logger.exception(
                "Failed to connect to any server, reconnecting in %d seconds...",
                RECONNECT_INTERVAL_SECONDS
            )
            await sleep(RECONNECT_INTERVAL_SECONDS)

    async def _authenticate(self, auth_lost_future):
        async def auth_lost_handler(error):
            logger.warning("WebSocket client authentication lost")
            auth_lost_future.set_exception(error)

        try:
            if self._steam_app_ownership_ticket_cache.ticket:
                await self._protocol_client.register_auth_ticket_with_cm(self._steam_app_ownership_ticket_cache.ticket)

            if self._user_info_cache.token:
                ret_code = await self._protocol_client.authenticate_token(self._user_info_cache.steam_id, self._user_info_cache.account_username, self._user_info_cache.token, auth_lost_handler)
            else:
                ret_code = None
                while ret_code != UserActionRequired.NoActionRequired:
                    if ret_code != None:
                        await self.communication_queues['plugin'].put({'auth_result': ret_code})
                        logger.info(f"Put {ret_code} in the queue, waiting for other side to receive")
                    response = await self.communication_queues['websocket'].get()
                    logger.info(f" Got {response.keys()} from queue")
                    password = response.get('password', None)
                    two_factor = response.get('two_factor', None)
                    logger.info(f'Authenticating with {"username" if self._user_info_cache.account_username else ""}, {"password" if password else ""}, {"two_factor" if two_factor else ""}')
                    ret_code = await self._protocol_client.authenticate_password(self._user_info_cache.account_username, password, two_factor, self._user_info_cache.two_step, auth_lost_handler)
                    logger.info(f"Response from auth {ret_code}")
            logger.info("Finished authentication")
            await self.communication_queues['plugin'].put({'auth_result': ret_code})

            # request new steam app ownership ticket
            await self._protocol_client.get_steam_app_ownership_ticket()

        except Exception as e:
            await self.communication_queues['errors'].put(e)
            raise e


