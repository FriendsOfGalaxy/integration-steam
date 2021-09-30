import base64
import logging

from persistent_cache_state import PersistentCacheState


logger = logging.getLogger(__name__)


class LocalMachineCache:

    def __init__(self, persistent_cache: dict, cache_state: PersistentCacheState):
        self._cache_state = cache_state
        self._persistent_cache = persistent_cache

    @property
    def machine_id(self) -> bytes:
        return base64.b64decode(self._persistent_cache.get('machine_id', ''))

    @machine_id.setter
    def machine_id(self, machine_id: bytes):
        self._persistent_cache['machine_id'] = base64.b64encode(machine_id).decode('utf-8')
        self._cache_state.modified = True
        logger.info("Set new machine ID: %s" % machine_id)

