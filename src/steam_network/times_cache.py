
from .cache_proto import ProtoCache
import logging

logger = logging.getLogger(__name__)


class TimesCache(ProtoCache):
    def __init__(self):
        super(TimesCache, self).__init__()
        self._games_to_import = []
        self._times_imported = True

    def start_game_times_import(self):
        self._info_map = dict()
        self._times_imported = False
        self._update_ready_state()

    @property
    def import_in_progress(self):
        self._update_ready_state()
        return not self._ready_event.is_set()

    def __iter__(self):
        yield from self._info_map.items()

    def times_import_finished(self, finished):
        self._times_imported = finished
        self._update_ready_state()

    def update_time(self, game_id, time_played, last_played):
        if game_id not in self._info_map:
            self._info_map[game_id] = dict()
        self._info_map[game_id]['time_played'] = time_played
        self._info_map[game_id]['last_played'] = last_played

    def _update_ready_state(self):
        if self._times_imported:
            if self._ready_event.is_set():
                return
            logger.info("Setting state to ready")
            self._ready_event.set()
        else:
            self._ready_event.clear()
