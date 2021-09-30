
from .cache_proto import ProtoCache
import logging

logger = logging.getLogger(__name__)


class StatsCache(ProtoCache):
    def __init__(self):
        super(StatsCache, self).__init__()
        self._games_to_import = []

    def start_game_stats_import(self, game_ids):
        for game_id in game_ids:
            self._info_map[game_id] = dict()
        self._games_to_import = game_ids
        self._update_ready_state()

    @property
    def import_in_progress(self):
        self._update_ready_state()
        return not self._ready_event.is_set()

    def __iter__(self):
        yield from self._info_map.items()

    def _check_remove(self, game_id):
        if 'stats' in self._info_map[game_id] \
                and 'achievements' in self._info_map[game_id]:
            self._games_to_import.remove(game_id)

    def update_stats(self, game_id, stats, achievements):
        if game_id not in self._info_map:
            self._info_map[game_id] = dict()
        self._info_map[game_id]['stats'] = stats
        self._info_map[game_id]['achievements'] = achievements

        self._check_remove(game_id)
        self._update_ready_state()

    def _update_ready_state(self):
        if len(self._games_to_import) == 0:
            if self._ready_event.is_set():
                return
            logger.info("Setting state to ready")
            self._ready_event.set()
        else:
            self._ready_event.clear()
