import asyncio
import json
import logging
import os
import platform
import random
import re
import subprocess
import sys
import webbrowser
from http.cookies import SimpleCookie, Morsel
from typing import Any, Dict, List

from galaxy.api.plugin import Plugin, create_and_run_plugin
from galaxy.api.types import (
    Achievement, Authentication, Cookie, FriendInfo, Game, GameTime, LicenseInfo, NextStep, LocalGame
)
from galaxy.api.errors import (
    AuthenticationRequired, UnknownBackendResponse, AccessDenied, InvalidCredentials, UnknownError
)
from galaxy.api.consts import Platform, LicenseType
from galaxy.api.jsonrpc import InvalidParams

import achievements_cache
from backend import SteamHttpClient, AuthenticatedHttpClient
from client import local_games_list, get_state_changes, get_client_executable, load_vdf, get_configuration_folder
from registry_monitor import get_steam_registry_monitor
from uri_scheme_handler import is_uri_handler_installed
from version import __version__
from cache import Cache

def is_windows():
    return platform.system().lower() == "windows"


LOGIN_URI = r"https://steamcommunity.com/login/home/?goto="
JS_PERSISTENT_LOGIN = r"document.getElementById('remember_login').checked = true;"
END_URI_REGEX = r"^https://steamcommunity.com/(profiles|id)/.*"

AUTH_PARAMS = {
    "window_title": "Login to Steam",
    "window_width": 640,
    "window_height": 462 if is_windows() else 429,
    "start_uri": LOGIN_URI,
    "end_uri_regex": END_URI_REGEX
}

def morsels_to_dicts(morsels):
    cookies = []
    for morsel in morsels:
        cookie = {
            "name": morsel.key,
            "value": morsel.value,
            "domain": morsel["domain"],
            "path": morsel["path"]
        }
        cookies.append(cookie)
    return cookies

def dicts_to_morsels(cookies):
    morsels = []
    for cookie in cookies:
        name = cookie["name"]
        value = cookie["value"]
        m = Morsel()
        m.set(name, value, value)
        m["domain"] = cookie.get("domain", "")
        m["path"] = cookie.get("path", "")
        morsels.append(m)
    return morsels

def parse_stored_cookies(cookies):
    if isinstance(cookies, dict):
        cookies = [{"name": key, "value": value} for key, value in cookies.items()]
    return dicts_to_morsels(cookies)

class SteamPlugin(Plugin):
    def __init__(self, reader, writer, token):
        super().__init__(Platform.Steam, __version__, reader, writer, token)
        self._own_games: List = []
        self._other_games: List[str] = []
        self._own_friends: List[FriendInfo] = []
        self._steam_id = None
        self._regmon = get_steam_registry_monitor()
        self._local_games_cache: List[LocalGame] = []
        self._http_client = AuthenticatedHttpClient()
        self._client = SteamHttpClient(self._http_client)
        self._achievements_cache = Cache()
        self._achievements_cache_updated = False
        self._achievements_semaphore = asyncio.Semaphore(20)

        self.create_task(self._update_local_games(), "Update local games")

    def _store_cookies(self, cookies):
        credentials = {
            "cookies": morsels_to_dicts(cookies)
        }
        self.store_credentials(credentials)

    @staticmethod
    def _create_two_factor_fake_cookie():
        return Cookie(
            # random SteamID with proper "instance", "type" and "universe" fields
            # (encoded in most significant bits)
            name="steamMachineAuth{}".format(random.randint(1, 2 ** 32 - 1) + 0x01100001 * 2 ** 32),
            # 40-bit random string encoded as hex
            value=hex(random.getrandbits(20 * 8))[2:].upper()
        )

    async def shutdown(self):
        self._regmon.close()
        await self._http_client.close()

    def handshake_complete(self):
        achievements_cache_ = self.persistent_cache.get("achievements")
        if achievements_cache_ is not None:
            try:
                achievements_cache_ = json.loads(achievements_cache_)
                self._achievements_cache = achievements_cache.from_dict(achievements_cache_)
            except Exception:
                logging.exception("Can not deserialize achievements cache")

    async def _do_auth(self, morsels):
        cookies = [(morsel.key, morsel) for morsel in morsels]

        self._http_client.update_cookies(cookies)
        self._http_client.set_cookies_updated_callback(self._store_cookies)
        self._force_utc()

        try:
            profile_url = await self._client.get_profile()
        except UnknownBackendResponse:
            raise InvalidCredentials()

        try:
            self._steam_id, login = await self._client.get_profile_data(profile_url)
        except AccessDenied:
            raise InvalidCredentials()

        self._http_client.set_auth_lost_callback(self.lost_authentication)

        return Authentication(self._steam_id, login)

    def _force_utc(self):
        cookies = SimpleCookie()
        cookies["timezoneOffset"] = "0,0"
        morsel = cookies["timezoneOffset"]
        morsel["domain"] = "steamcommunity.com"
        # override encoding (steam does not fallow RFC 6265)
        morsel.set("timezoneOffset", "0,0", "0,0")
        self._http_client.update_cookies(cookies)

    async def authenticate(self, stored_credentials=None):
        if not stored_credentials:
            return NextStep(
                "web_session",
                AUTH_PARAMS,
                [self._create_two_factor_fake_cookie()],
                {re.escape(LOGIN_URI): [JS_PERSISTENT_LOGIN]}
            )

        cookies = stored_credentials.get("cookies", [])
        morsels = parse_stored_cookies(cookies)
        return await self._do_auth(morsels)

    async def pass_login_credentials(self, step, credentials, cookies):
        try:
            morsels = dicts_to_morsels(cookies)
        except Exception:
            raise InvalidParams()

        auth_info = await self._do_auth(morsels)
        self._store_cookies(morsels)
        return auth_info

    async def get_owned_games(self):
        if self._steam_id is None:
            raise AuthenticationRequired()

        games = await self._client.get_games(self._steam_id)

        owned_games = []

        try:
            for game in games:
                owned_games.append(
                    Game(
                        str(game["appid"]),
                        game["name"],
                        [],
                        LicenseInfo(LicenseType.SinglePurchase, None)
                    )
                )
        except (KeyError, ValueError):
            logging.exception("Can not parse backend response")
            raise UnknownBackendResponse()


        self._own_games = games
        
        game_ids = list(map(lambda x: x.game_id, owned_games))
        other_games = await self.get_steam_sharing_games(game_ids)
        for i in other_games:
            owned_games.append(i)

        return owned_games

    async def get_steam_sharing_games(self,owngames: List[str]) -> List[Game]:
        profiles = list(filter(lambda x: "!" in x.user_name, self._own_friends))
        newgames: List[Game] = []
        self._other_games = []
        for i in profiles:
            othergames = await self._client.get_games(i.user_id)

            try:
                for game in othergames:
                    hasit = any(f == str(game["appid"]) for f in owngames) or any(f.game_id == str(game["appid"]) for f in newgames)
                    if not hasit:
                        self._ither_games.append(str(game["appid"]))
                        newgame = Game(
                            str(game["appid"]),
                            game["name"],
                            [],
                            LicenseInfo(LicenseType.OtherUserLicense, i.user_name)
                        )
                        newgames.append(newgame)
            except (KeyError, ValueError):
                logging.exception("Can not parse backend response")
                raise UnknownBackendResponse()
        return newgames

    async def prepare_game_times_context(self, game_ids: List[str]) -> Any:
        if self._steam_id is None:
            raise AuthenticationRequired()

        return await self._get_game_times_dict()

    async def get_game_time(self, game_id: str, context: Any) -> GameTime:
        game_time = context.get(game_id)
        if game_time is None:
            logging.exception("Game {} not owned".format(game_id))
        return game_time

    async def _get_game_times_dict(self) -> Dict[str, GameTime]:
        games = self._own_games

        game_times = {}

        try:
            for game in games:
                game_id = str(game["appid"])
                last_played = game.get("last_played")
                if last_played == 86400:
                    # 86400 is used as sentinel value for games no supporting last_played
                    last_played = None
                game_times[game_id] = GameTime(
                    game_id,
                    int(float(game.get("hours_forever", "0").replace(",", "")) * 60),
                    last_played
                )
        except (KeyError, ValueError):
            logging.exception("Can not parse backend response")
            raise UnknownBackendResponse()

        try:
            steamFolder = get_configuration_folder()
            accountId = str( int(self._steam_id) - 76561197960265728  )
            vdfFile = os.path.join(steamFolder, "userdata", accountId, "config", "localconfig.vdf")
            logging.debug(vdfFile)
            data = load_vdf(vdfFile)
            timedata = data["UserLocalConfigStore"]["Software"]["Valve"]["Steam"]["Apps"]
            for gameid in self.otherGames:
                playTime = 0
                lastPlayed = 86400
                if gameid in timedata:
                    item = timedata[gameid]
                    if 'playtime' in item:
                        playTime = item["playTime"]
                    if 'lastplayed' in item:
                        lastPlayed = item["LastPlayed"]
                game_times[gameid] = GameTime(gameid, playTime, lastPlayed)
        except (KeyError, ValueError):
            logging.exception("Can not parse friend games")

        return game_times

    async def prepare_achievements_context(self, game_ids: List[str]) -> Any:
        if self._steam_id is None:
            raise AuthenticationRequired()

        return await self._get_game_times_dict()

    async def get_unlocked_achievements(self, game_id: str, context: Any) -> List[Achievement]:
        game_time = await self.get_game_time(game_id, context)
        if game_time.time_played == 0:
            return []

        fingerprint = achievements_cache.Fingerprint(game_time.last_played_time, game_time.time_played)
        achievements = self._achievements_cache.get(game_id, fingerprint)

        if achievements is not None:
            # return from cache
            return achievements

        # fetch from backend and update cache
        achievements = await self._get_achievements(game_id)
        self._achievements_cache.update(game_id, achievements, fingerprint)
        self._achievements_cache_updated = True
        return achievements

    def achievements_import_complete(self) -> None:
        if self._achievements_cache_updated:
            self.push_cache()
            self._achievements_cache_updated = False

    async def _get_achievements(self, game_id):
        async with self._achievements_semaphore:
            achievements = await self._client.get_achievements(self._steam_id, game_id)
            return [Achievement(unlock_time, None, name) for unlock_time, name in achievements]

    async def get_friends(self):
        if self._steam_id is None:
            raise AuthenticationRequired()

        self._own_friends = [
            FriendInfo(user_id=user_id, user_name=user_name)
            for user_id, user_name in (await self._client.get_friends(self._steam_id)).items()
        ]
        
        return self._own_friends

    def tick(self):
        if self._regmon.is_updated():
            self.create_task(self._update_local_games(), "Update local games")

    async def _update_local_games(self):
        loop = asyncio.get_running_loop()
        new_list = await loop.run_in_executor(None, local_games_list)
        notify_list = get_state_changes(self._local_games_cache, new_list)
        self._local_games_cache = new_list
        for local_game_notify in notify_list:
            self.update_local_game_status(local_game_notify)

    async def get_local_games(self):
        return self._local_games_cache

    @staticmethod
    def _steam_command(command, game_id):
        if is_uri_handler_installed("steam"):
            webbrowser.open("steam://{}/{}".format(command, game_id))
        else:
            webbrowser.open("https://store.steampowered.com/about/")

    async def launch_game(self, game_id):
        SteamPlugin._steam_command("launch", game_id)

    async def install_game(self, game_id):
        SteamPlugin._steam_command("install", game_id)

    async def uninstall_game(self, game_id):
        SteamPlugin._steam_command("uninstall", game_id)

    async def shutdown_platform_client(self) -> None:
        if is_windows():
            exe = get_client_executable()
            if exe is None:
                return
            cmd = '"{}" -shutdown -silent'.format(exe)
        else:
            cmd = "osascript -e 'quit app \"Steam\"'"
        logging.debug("Running command '%s'", cmd)
        process = await asyncio.create_subprocess_shell(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await process.communicate()


def main():
    create_and_run_plugin(SteamPlugin, sys.argv)


if __name__ == "__main__":
    main()
