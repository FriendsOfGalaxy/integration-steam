import json
import logging
import time
from typing import Dict, Any, Optional

from persistent_cache_state import PersistentCacheState


CACHE_KEY = 'websocket_cache'
CACHE_ENTRY_TIMEOUT_DAYS = 30
SECONDS_IN_A_DAY = 86400

logger = logging.getLogger(__name__)


class CachePersistenceException(Exception):
    def __init__(self, message: str):
        self.message = message


class WebSocketCachePersistence:
    def __init__(
            self,
            persistent_cache: Dict[str, Any],
            persistent_cache_state: PersistentCacheState
    ):
        self._persistent_cache = persistent_cache
        self._persistent_cache_state = persistent_cache_state

    def read(self, cell_id: int) -> Optional[str]:
        try:
            cache = self._deserialize_cache()
            self._validate_cache(cache, cell_id)

            server = cache[str(cell_id)]['server']
            logger.info(f"websocket_cache returned server: {server}")
            return server
        except CachePersistenceException as e:
            logger.info(e.message)
            return None
        except Exception as e:
            logger.warning(f"Error while reading websocket_cache: {str(e)}")
            return None

    def write(self, cell_id: int, server: str) -> None:
        self._clean_up_servers_cache()
        logger.debug(f"Storing server in cache {server} at cell {cell_id}")
        cache = self._deserialize_cache()

        cache[cell_id] = {
            'server': server,
            'timeout': time.time() + CACHE_ENTRY_TIMEOUT_DAYS * SECONDS_IN_A_DAY
        }

        self._persistent_cache[CACHE_KEY] = json.dumps(cache)
        self._persistent_cache_state.modified = True

    def _deserialize_cache(self) -> dict:
        cache_json = self._persistent_cache.get(CACHE_KEY, 'null')
        return json.loads(cache_json)

    @staticmethod
    def _validate_cache(cache: dict, cell_id: int) -> None:
        if cache is None:
            raise CachePersistenceException("websocket_cache entry was not found in cache")

        cell_id_cache = cache.get(str(cell_id), None)
        if cell_id_cache is None:
            raise CachePersistenceException(f"No websocket_cache for cell id: {cell_id}")

        if 'server' not in cell_id_cache:
            raise CachePersistenceException(f"server was not found in websocket_cache entry {cell_id_cache}")

        if 'timeout' not in cell_id_cache:
            raise CachePersistenceException(f"timeout was not found in websocket_cache entry {cell_id_cache}")

        if cell_id_cache['timeout'] < time.time():
            raise CachePersistenceException(f"websocket_cache entry expired {cell_id_cache}")

    # TODO: Temporary clean up, remove after 2021-08-01
    # https://github.com/FriendsOfGalaxy/galaxy-integration-steam/pull/108
    def _clean_up_servers_cache(self):
        if 'servers_cache' in self._persistent_cache:
            logger.info("Removing 'servers_cache' from persistent_cache")
            self._persistent_cache.pop('servers_cache')
