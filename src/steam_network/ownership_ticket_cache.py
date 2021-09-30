import base64

from persistent_cache_state import PersistentCacheState



class OwnershipTicketCache:
    """
    Simple cache created to store ticket for Steam App ownership ticket.
    If there is need to waiting for ticket the cache should be inherited over `ProtoCache`
    """
    def __init__(self, persistent_cache: dict, cache_state: PersistentCacheState):
        self._cache_state = cache_state
        self._persistent_cache = persistent_cache

    @property
    def ticket(self) -> bytes:
        return base64.b64decode(self._persistent_cache.get('ownership_ticket', ''))

    @ticket.setter
    def ticket(self, ticket: bytes):
        self._persistent_cache['ownership_ticket'] = base64.b64encode(ticket).decode('utf-8')
        self._cache_state.modified = True
