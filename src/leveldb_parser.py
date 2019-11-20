import platform
import logging as log
import json
import os
from dataclasses import dataclass
# Mapping of https://store.steampowered.com/api/appdetails/?appids={}&filters=categories response to local steam values
TAGS_MAPPING = {
                    28: 1,  # 'Controllers (full)'},
                    18: 2,  # 'Controllers (partial)'},
                    None: 3,  # 'VR',
                    29: 4,  # 'Trading cards'},
                    30: 5,  # 'Workshop'},
                    22: 6 ,  #: 'Achievements'},
                    2: 7 ,  #: 'Single player'},
                    1: 8,  #: 'Multiplayer'},
                    36: 8,
                    9: 9  #: 'Cooperative'}
}

@dataclass
class COLLECTIONS_MAP:
    UNUSED_0 = 0
    PLAY_STATE = 1
    PLAYER = 2
    UNUSED_3 = 3
    CATEGORIES = 4

class LevelDbParser():
    def __init__(self, miniprofile_id):
        self._miniprofile_id = miniprofile_id
        self._collections = []
        self._dynamic_collections = {}
        self._lvl_db_available = None

    @property
    def lvl_db_is_present(self):
        return self._lvl_db_available

    def _collection_is_deleted(self, collection):
        if 'is_deleted' not in collection:
            return False
        else:
            return collection['is_deleted']

    def _read_db_log_file(self, level_db_dir, encoding="utf-8"):
        for db_file in os.listdir(level_db_dir):
            if db_file.endswith('.log'):
                db_log_file = open(os.path.join(level_db_dir, db_file), 'r', errors="replace", encoding=encoding)
        db_log_file = db_log_file.read()
        return db_log_file

    def _retrieve_jsons(self, db_log_file):
        decoder = json.JSONDecoder()
        collections_list = []

        def find_last_meta_miniprofile_pair():
            meta_entries = []
            current_pos = 0
            future_pos = 0
            log.info(f"Looking for last META entry  + user id pair for miniprofile id {self._miniprofile_id}")
            while future_pos != -1:
                future_pos = db_log_file.find("META:https://steamloopback.host", current_pos)
                if future_pos != -1:
                    current_pos = future_pos + 1
                    meta_entries.append(future_pos)

            log.info(f"Meta entries {meta_entries}")

            for index, meta_entry in reversed(list(enumerate(meta_entries))):
                user_id = db_log_file.find(str(self._miniprofile_id), meta_entry)
                log.info(f"User_id {user_id} meta_entry {meta_entries[index]}, index {index}")
                # Ensure its not a dummy entry
                if db_log_file.find('showcases-version', meta_entry) < 0:
                    continue
                if user_id != -1:
                    if index == len(meta_entries) - 1:
                        return user_id, -1
                    else:
                        return user_id, meta_entries[index+1]

        user_json_start, user_json_end = find_last_meta_miniprofile_pair()

        if user_json_start == -1:
            log.info("No user entry in lvldb")
            return []
        if user_json_end == -1:
            log.info("User json is the last entry in lvldb")
            user_json_end = len(db_log_file)

        log.info(f"User json start {user_json_start} end {user_json_end}")
        while True:
            match = db_log_file.find('{', user_json_start)
            if user_json_end > 0 and  match >= user_json_end:
                break
            if match == -1:
                break
            try:
                result, index = decoder.raw_decode(db_log_file[match:])
                collections_list.append(result)
                user_json_start = match + index
            except ValueError:
                user_json_start = match + 1
        log.info(f"Retrieved Jsons from lvldb {collections_list}")
        return collections_list

    def parse_leveldb(self):
        if platform.system() == "Windows":
            level_db_dir = os.path.join(os.path.expandvars(r'%LOCALAPPDATA%'), r"Steam\htmlcache\Local Storage\leveldb")
        else:
            level_db_dir = os.path.join(os.path.expandvars(r'$HOME'), r"Library/Application Support/Steam/config/htmlcache/Local Storage/leveldb")

        try:
            db_log_file = self._read_db_log_file(level_db_dir)
            collections_list = self._retrieve_jsons(db_log_file)
            if not collections_list:
                db_log_file = self._read_db_log_file(level_db_dir, "utf-16-be")
                collections_list = self._retrieve_jsons(db_log_file)
        except:
            log.warning("Unable to read db file, possibly non existent")
            self._lvl_db_available = False
            return []
        else:
            self._lvl_db_available = True

        if not collections_list:
            log.warning("Empty collections list")
            return []
        fresh_collections_list = []
        pretenders_list = {}

        for collection in collections_list:
            if 'key' in collection and 'timestamp' in collection:
                if collection['key'] not in pretenders_list:
                    pretenders_list[collection['key']] = collection
                else:
                    if collection['timestamp'] > pretenders_list[collection['key']]['timestamp']:
                        pretenders_list[collection['key']] = collection

        for pretender in pretenders_list:
            fresh_collections_list.append(pretenders_list[pretender])

        if not fresh_collections_list:
            log.warning(f"Empty collections json")
            return []

        collections = []
        for collections_object in fresh_collections_list:
            if 'value' in collections_object and not self._collection_is_deleted(collections_object):
                collections.append(json.loads(collections_object['value']))

        if not collections:
            log.warning(f"Empty collections list inside collections json")
            return []
        else:
            self._collections = collections

        log.info(f"Parsed lvldb {collections}")

    def get_static_collections_tags(self):

        game_settings = {}
        for collection in self._collections:
            if not isinstance(collection, dict):
                continue
            if 'name' in collection and 'added' in collection and collection['added']:
                if collection['id'] in ('favorite' 'hidden'):
                    collection_name = collection['id']
                else:
                    collection_name = collection['name']
                for game in collection['added']:
                    if str(game) not in game_settings:
                        game_settings[str(game)] = [collection_name]
                    else:
                        game_settings[str(game)].append(collection_name)
        log.info(f"Static collections tags from leveldb {game_settings}")
        return game_settings

    def parse_dynamic_collections(self):
        dynamic_collections = {}
        for collection in self._collections:
            if not isinstance(collection, dict):
                continue
            if 'name' in collection and 'filterSpec' in collection:
                for group_num, filter_group in enumerate(collection['filterSpec']['filterGroups'], start=0):
                    if not collection['name'] in dynamic_collections:
                        dynamic_collections[collection['name']] = {group_num: filter_group['rgOptions']}
                    else:
                        dynamic_collections[collection['name']][group_num] = filter_group['rgOptions']

        self._dynamic_collections = dynamic_collections

    def dynamic_collection_can_be_processed(self, collection):
        empty = True
        for rg_group in collection:
            if collection[rg_group]:
                if rg_group == 0:
                    # Unused field, only one with 'bAcceptUnion': True
                    empty = False
                    return False
                if rg_group == 1:
                    # Play State tags ("Installed" etc) , not taken into consideration
                    empty = False
                    return False
                if rg_group == 2:
                    # temp
                    empty = False
                    if 3 in collection[rg_group]:
                        # VR tag, unsupported atm
                        return False
                if rg_group == 3:
                    # Empty field
                    empty = False
                    return False
                if rg_group == 4:
                    empty = False
        if empty:
            return False
        return True

    def translate_player_tags(self, game_tags):
        translated_game_tags = []
        for game_tag in game_tags:
            translated_game_tags.append(TAGS_MAPPING[game_tag['id']])
        return translated_game_tags

    def _dynamic_tags_match(self, collection_tags, game_tags):
        for dynamic_tag in collection_tags:
            if dynamic_tag not in game_tags:
                return False
        return True

    def get_blacklisted_tags(self):
        collections = self._dynamic_collections
        blacklisted_tags = []
        for collection in collections:
            for rg_group in collections[collection]:
                if collections[collection][rg_group]:
                    if rg_group == 1:
                        # Play State tags ("Installed" etc) , not taken into consideration
                        blacklisted_tags.append(collection)
        return blacklisted_tags

    def get_dynamic_tags_for_game(self, game):
        collections = self._dynamic_collections
        game_in_collections = []
        log.info(f"Collections {collections}")
        try:
            for collection in collections:
                if self.dynamic_collection_can_be_processed(collections[collection]):
                    if not self._dynamic_tags_match(collections[collection][COLLECTIONS_MAP.CATEGORIES], game['tags']):
                        log.info(f"Store Tags not matching fully for {collection}, and {game['tags']}")
                        continue

                    if collections[collection][COLLECTIONS_MAP.PLAYER]:

                        game_translated_player_tags = self.translate_player_tags(game['categories'])
                        log.info(f"Translated game tags vs real tags {game_translated_player_tags}, {game['categories']}")

                        if not self._dynamic_tags_match(collections[collection][COLLECTIONS_MAP.PLAYER], game_translated_player_tags):
                            log.info(f"Player Tags not matching fully for {collection}, {collections[collection][COLLECTIONS_MAP.PLAYER]} vs {game_translated_player_tags}")
                            continue

                    game_in_collections.append(collection)
        except Exception as e:
            log.warning(f"Exception on retrieving dynamic tags for game {repr(e)}")
            return []
        return game_in_collections
