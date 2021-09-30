import logging
from typing import List, AsyncGenerator, Dict
import time

import yarl

from .steam_http_client import SteamHttpClient


logger = logging.getLogger(__name__)

Timeout = float
HostName = str


def current_time() -> float:
    return time.time()


class WebSocketList:
    def __init__(self, http_client: SteamHttpClient):
        self._http_client = http_client
        self._servers_blacklist: Dict[HostName, Timeout] = {}
    
    @staticmethod 
    def __host_name(url: str) -> HostName:
        return yarl.URL(url).host
    
    def add_server_to_ignored(self, socket_addr: str, timeout_sec: int):
        self._servers_blacklist[self.__host_name(socket_addr)] = current_time() + timeout_sec

    async def _fetch_new_list(self, cell_id: int) -> List[str]:
        servers = await self._http_client.get_servers(cell_id)
        logger.debug("Got servers from backend: %s", str(servers))
        return [f"wss://{server}/cmsocket/" for server in servers]

    async def get(self, cell_id: int) -> AsyncGenerator[str, None]:
        sockets = await self._fetch_new_list(cell_id)
        for socket in sockets:
            if current_time() > self._servers_blacklist.get(self.__host_name(socket), 0):
                yield socket
            else:
                logger.info("Omitting blacklisted server %s", socket)
