import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import aiohttp
from yarl import URL
from requests_html import HTML
from galaxy.api.errors import AuthenticationRequired, UnknownBackendResponse, AccessDenied
from galaxy.http import HttpClient

def is_absolute(url):
    return bool(urlparse(url).netloc)

class CookieJar(aiohttp.CookieJar):
    def __init__(self):
        super().__init__()
        self._cookies_updated_callback = None

    def set_cookies_updated_callback(self, callback):
        self._cookies_updated_callback = callback

    def update_cookies(self, cookies, url=URL()):
        super().update_cookies(cookies, url)
        if cookies and self._cookies_updated_callback:
            self._cookies_updated_callback(list(self))

class AuthenticatedHttpClient(HttpClient):
    def __init__(self):
        self._auth_lost_callback = None
        self._cookie_jar = CookieJar()
        super().__init__(cookie_jar=self._cookie_jar)

    def set_auth_lost_callback(self, callback):
        self._auth_lost_callback = callback

    def set_cookies_updated_callback(self, callback):
        self._cookie_jar.set_cookies_updated_callback(callback)

    def update_cookies(self, cookies):
        self._cookie_jar.update_cookies(cookies)

    async def get(self, *args, **kwargs):
        try:
            response = await super().request("GET", *args, **kwargs)
        except AuthenticationRequired:
            self._auth_lost()

        html = await response.text(encoding="utf-8", errors="replace")
        # "Login" button in menu
        if html.find('class="menuitem" href="https://store.steampowered.com/login/') != -1:
            self._auth_lost()

        return response

    def _auth_lost(self):
        if self._auth_lost_callback:
            self._auth_lost_callback()
        raise AccessDenied()


class SteamHttpClient:
    def __init__(self, http_client):
        self._http_client = http_client

    async def get_profile(self):
        url = "https://steamcommunity.com/"
        response = await self._http_client.get(url, allow_redirects=True)
        text = await response.text()

        def parse(text):
            html = HTML(html=text)
            profile_url = html.find("a.user_avatar", first=True)
            if not profile_url:
                raise UnknownBackendResponse()
            try:
                return profile_url.attrs["href"]
            except KeyError:
                return UnknownBackendResponse()

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, parse, text)

    async def get_profile_data(self, url):
        response = await self._http_client.get(url, allow_redirects=True)
        text = await response.text()

        def parse(text):
            # find login
            start = re.search('data-miniprofile="(\d+)">', text).end()
            if start == -1:
                raise UnknownBackendResponse()
            end = text.find('</a>', start)
            login = text[start:end]

            # find steam id
            variable = 'g_steamID = "'
            start = text.find(variable)
            if start == -1:
                raise UnknownBackendResponse()
            start += len(variable)
            end = text.find('";', start)
            steam_id = text[start:end]

            return steam_id, login

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, parse, text)

    async def get_games(self, steam_id):
        url = "https://steamcommunity.com/profiles/{}/games/?tab=all".format(steam_id)
        response = await self._http_client.get(url)

        # find js array with games
        text = await response.text()
        variable = "var rgGames ="
        start = text.find(variable)
        if start == -1:
            raise UnknownBackendResponse()
        start += len(variable)
        end = text.find(";\r\n", start)
        array = text[start:end]

        try:
            games = json.loads(array)
        except json.JSONDecodeError:
            raise UnknownBackendResponse()

        return games

    @staticmethod
    def parse_date(text_time):
        def try_parse(text, date_format):
            d = datetime.strptime(text, date_format)
            return datetime.combine(d.date(), d.time(), timezone.utc)

        formats = (
            "Unlocked %d %b, %Y @ %I:%M%p",
            "Unlocked %d %b @ %I:%M%p",
            "Unlocked %b %d, %Y @ %I:%M%p",
            "Unlocked %b %d @ %I:%M%p"
        )
        for date_format in formats:
            try:
                date = try_parse(text_time, date_format)
                if date.year == 1900:
                    date = date.replace(year=datetime.utcnow().year)
                return date
            except ValueError:
                continue
            logging.exception("Unexpected date format: {}. Please report to the developers".format(text_time))
            raise UnknownBackendResponse()

    async def get_achievements(self, steam_id, game_id):
        host = "https://steamcommunity.com"
        url = host + "/profiles/{}/stats/{}/".format(steam_id, game_id)
        params = {
            "tab": "achievements",
            "l": "english"
        }
        # manual redirects, append params
        while True:
            response = await self._http_client.get(url, allow_redirects=False, params=params)
            if 300 <= response.status and response.status < 400:
                url = response.headers["Location"]
                if not is_absolute(url):
                    url = host + url
                continue
            break

        text = await response.text()

        def parse(text):
            html = HTML(html=text)
            rows = html.find(".achieveRow")
            achievements = []
            try:
                for row in rows:
                    unlock_time = row.find(".achieveUnlockTime", first=True)
                    if unlock_time is None:
                        continue
                    unlock_time = int(self.parse_date(unlock_time.text).timestamp())
                    name = row.find("h3", first=True).text
                    achievements.append((unlock_time, name))
            except (AttributeError, ValueError, TypeError):
                logging.exception("Can not parse backend response")
                raise UnknownBackendResponse()

            return achievements

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, parse, text)

    async def get_friends(self, steam_id):
        response = await self._http_client.get(
            "https://steamcommunity.com/profiles/{}/friends/".format(steam_id),
            params={"l": "english", "ajax": 1}
        )

        def parse_response(text):
            def parse_id(profile):
                return profile.attrs["data-steamid"]

            def parse_name(profile):
                return HTML(html=profile.html).find(".friend_block_content", first=True).text.split("\nLast Online")[0]

            try:
                search_results = HTML(html=text).find("#search_results", first=True).html
                return {
                    parse_id(profile): parse_name(profile)
                    for profile in HTML(html=search_results).find(".friend_block_v2")
                }
            except (AttributeError, ValueError, TypeError):
                logging.exception("Can not parse backend response")
                raise UnknownBackendResponse()

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, parse_response, await response.text(encoding="utf-8", errors="replace"))
