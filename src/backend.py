import asyncio
import json
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse
import vdf

import aiohttp
from galaxy.api.errors import AccessDenied, AuthenticationRequired, UnknownBackendResponse, UnknownError, BackendError
from galaxy.http import HttpClient
from requests_html import HTML
from yarl import URL


def is_absolute(url):
    return bool(urlparse(url).netloc)


async def get_text(response: aiohttp.ClientResponse) -> str:
    return await response.text(encoding="utf-8", errors="replace")


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

        html = await get_text(response)
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
        text = await get_text(await self._http_client.get(url, allow_redirects=True))

        def parse(text):
            html = HTML(html=text)
            profile_url = html.find("a.user_avatar", first=True)
            if not profile_url:
                logging.error("Can not parse backend response - no a.user_avatar")
                raise UnknownBackendResponse()
            try:
                return profile_url.attrs["href"]
            except KeyError:
                logging.exception("Can not parse backend response")
                return UnknownBackendResponse()

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, parse, text)

    async def get_profile_data(self, url):
        text = await get_text(await self._http_client.get(url, allow_redirects=True))

        def parse(text, user_profile_url):
            html = HTML(html=text)
            # find persona_name
            div = html.find("div.profile_header_centered_persona", first=True)
            if not div:
                logging.error("Can not parse backend response - no div.profile_header_centered_persona")
                raise UnknownBackendResponse()
            span = div.find("span.actual_persona_name", first=True)
            if not span:
                logging.error("Can not parse backend response - no span.actual_persona_name")
                raise UnknownBackendResponse()
            persona_name = span.text

            # find steam id
            variable = 'g_steamID = "'
            start = text.find(variable)
            if start == -1:
                logging.error("Can not parse backend response - no g_steamID variable")
                raise UnknownBackendResponse()
            start += len(variable)
            end = text.find('";', start)
            steam_id = text[start:end]

            # find miniprofile id
            profile_link = f'{user_profile_url}" data-miniprofile="'
            start = text.find(profile_link)
            if start == -1:
                logging.error("Can not parse backend response - no steam profile href")
                raise UnknownBackendResponse()
            start += len(profile_link)
            end = text.find('">', start)
            miniprofile_id = text[start:end]

            return steam_id, miniprofile_id, persona_name

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, parse, text, url)

    async def get_games(self, steam_id):
        url = "https://steamcommunity.com/profiles/{}/games/?tab=all".format(steam_id)

        # find js array with games
        text = await get_text(await self._http_client.get(url))
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
            logging.exception("Can not parse backend response")
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

        logging.error("Unexpected date format: {}. Please report to the developers".format(text_time))
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

        text = await get_text(response)

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
        return await loop.run_in_executor(
            None,
            parse_response,
            await get_text(
                await self._http_client.get(
                    "https://steamcommunity.com/profiles/{}/friends/".format(steam_id),
                    params={"l": "english", "ajax": 1}
                )
            )
        )

    async def get_game_library_settings_file(self):
        remotestorageapp = await self._http_client.get(
            "https://store.steampowered.com/account/remotestorageapp/?appid=7")
        remotestorageapp_text = await remotestorageapp.text(encoding="utf-8", errors="replace")
        start_index = remotestorageapp_text.find("sharedconfig.vdf")
        if start_index == -1:
            # Fresh user, has no sharedconfig
            return []
        url_start = remotestorageapp_text.find('href="', start_index)
        url_end = remotestorageapp_text.find('">', url_start)
        url = remotestorageapp_text[int(url_start) + len('href="'): int(url_end)]
        sharedconfig = vdf.loads(await get_text(await self._http_client.get(url, allow_redirects=True)))
        logging.info(f"Sharedconfig file contents {sharedconfig}")
        try:
            apps = sharedconfig["UserRoamingConfigStore"]["Software"]["Valve"]["Steam"]["Apps"]
        except KeyError:
            logging.warning('Cant read users sharedconfig, assuming no tags set')
            return []
        game_settings = []
        for app in apps:
            tags = []
            if "tags" in apps[app]:
                for tag in apps[app]["tags"]:
                    tags.append(apps[app]['tags'][tag])
            hidden = True if "Hidden" in apps[app] and apps[app]['Hidden'] == '1' else False
            game_settings.append({'game_id': app, 'tags': tags, 'hidden': hidden})
        return game_settings

    async def get_store_popular_tags(self):
        popular_tags = await self._http_client.get("https://store.steampowered.com/tagdata/populartags/english")
        popular_tags = await popular_tags.json()
        return popular_tags

    async def get_game_tags(self, appid):
        try:
            game_info = await self._http_client.get(f"https://store.steampowered.com/broadcast/ajaxgetappinfoforcap?appid={appid}&l=english")
            game_info = await game_info.json()
        except (UnknownError, BackendError):
            logging.info(f"No store tags defined for {appid}")
            return {}
        tags = {}

        if "tags" in game_info:
            for tag in game_info["tags"]:
                if "browseable" in tag and tag["browseable"]:
                    tags[tag["tagid"]] = tag["name"]

        return tags

    async def get_game_categories(self, appid):
        try:
            game_info = await self._http_client.get(f"https://store.steampowered.com/api/appdetails/?appids={appid}&filters=categories&l=english")
            game_info = await game_info.json()
        except (UnknownError, BackendError):
            logging.info(f"No details defined for {appid}")
            return []
        if str(appid) in game_info and 'data' in game_info[str(appid)] and 'categories' in game_info[str(appid)]['data']:
            return game_info[str(appid)]['data']['categories']
        return []

