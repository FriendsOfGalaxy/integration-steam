import asyncio
from typing import Dict

from abc import abstractmethod
import logging

logger = logging.getLogger(__name__)


class ProtoCache:
    def __init__(self):
        self._pending_map: Dict = {}
        self._info_map: Dict = {}
        self._ready_event = asyncio.Event()
        self._new = True
        self.updated_handler = None
        self.added_handler = None
        self.removed_handler = None

    @abstractmethod
    def _reset(self, args):
        pass

    def reset(self, args):
        self._reset(args)
        self._update_ready_state()  # set if empty

    @abstractmethod
    def _add(self, args):
        pass

    def add(self, args):
        self._add(args)
        self._update_ready_state()

    @abstractmethod
    def _remove(self, args):
        pass

    def remove(self, args):
        self._remove(args)
        self._update_ready_state()

    @abstractmethod
    def update(self, **kwargs):
        pass

    @property
    def ready(self):
        return self._ready_event.is_set()

    async def wait_ready(self, timeout=None):
        try:
            await asyncio.wait_for(self._ready_event.wait(), timeout)
        except asyncio.TimeoutError:
            logger.info("Timed out waiting for games cache to get ready")

    def get(self, key, default=None):
        result = self._info_map.get(key, default)
        return result

    def __getitem__(self, key):
        result = self._info_map.get(key)
        if result is not None:
            return result
        else:
            raise KeyError(f"No {key} present")

    def get_keys(self):
        yield from self._info_map.keys()

    def __iter__(self):
        yield from self._info_map.items()

    def __contains__(self, identifier):
        return identifier in self._info_map

    def _update_ready_state(self):
        if not self._pending_map:
            self._ready_event.set()
        else:
            self._ready_event.clear()

    def __len__(self):
        return len(self._info_map)