import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Tuple
from urllib.parse import urlparse
import vdf
from galaxy.api.types import UserInfo

import aiohttp
from galaxy.api.errors import (
    UnknownBackendResponse,
    UnknownError,
    BackendError,
)
from requests_html import HTML


logger = logging.getLogger(__name__)


class UnfinishedAccountSetup(Exception):
    pass


def is_absolute(url):
    return bool(urlparse(url).netloc)


async def get_text(response: aiohttp.ClientResponse) -> str:
    return await response.text(encoding="utf-8", errors="replace")


class SteamHttpClient:
    def __init__(self, http_client):
        self._http_client = http_client

    async def get_steamcommunity_response_status(self):
        url = "https://steamcommunity.com"
        response = await self._http_client.get(url, allow_redirects=True)
        return response.status

    async def get_profile(self):
        url = "https://steamcommunity.com/"
        text = await get_text(await self._http_client.get(url, allow_redirects=True))

        def parse(text):
            html = HTML(html=text)
            profile_url = html.find("a.user_avatar", first=True)
            if not profile_url:
                logger.error("Can not parse backend response - no a.user_avatar")
                raise UnknownBackendResponse()
            try:
                return profile_url.attrs["href"]
            except KeyError:
                logger.exception("Can not parse backend response")
                return UnknownBackendResponse()

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, parse, text)

    async def get_profile_data(self, url):
        text = await get_text(await self._http_client.get(url, allow_redirects=True))

        def parse(text):
            html = HTML(html=text)
            # find persona_name
            div = html.find("div.profile_header_centered_persona", first=True)
            if not div:
                fallback_div = html.find("div.welcome_header_ctn")
                if fallback_div:
                    logger.info("Fresh account without set up steam profile.")
                    raise UnfinishedAccountSetup()
                logger.error(
                    "Can not parse backend response - no div.profile_header_centered_persona"
                )
                raise UnknownBackendResponse()
            span = div.find("span.actual_persona_name", first=True)
            if not span:
                logger.error("Can not parse backend response - no span.actual_persona_name")
                raise UnknownBackendResponse()
            persona_name = span.text

            # find miniprofile id
            miniprofile_element = html.find("div.playerAvatar", first=True)
            miniprofile_id = miniprofile_element.attrs.get("data-miniprofile")

            return miniprofile_id, persona_name

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, parse, text)

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
            logger.exception("Can not parse backend response")
            raise UnknownBackendResponse()

        return games

    async def setup_steam_profile(self, profile_url):
        url = profile_url.split("/home")[0]
        url += "/edit?welcomed=1"
        await self._http_client.get(url, allow_redirects=True)

    @staticmethod
    def parse_date(text_time):
        def try_parse(text, date_format):
            d = datetime.strptime(text, date_format)
            return datetime.combine(d.date(), d.time(), timezone.utc)

        formats = (
            "Unlocked %d %b, %Y @ %I:%M%p",
            "Unlocked %d %b @ %I:%M%p",
            "Unlocked %b %d, %Y @ %I:%M%p",
            "Unlocked %b %d @ %I:%M%p",
        )
        for date_format in formats:
            try:
                date = try_parse(text_time, date_format)
                if date.year == 1900:
                    date = date.replace(year=datetime.utcnow().year)
                return date
            except ValueError:
                continue

        logger.error(
            "Unexpected date format: {}. Please report to the developers".format(text_time)
        )
        raise UnknownBackendResponse()

    async def get_achievements(self, steam_id, game_id):
        host = "https://steamcommunity.com"
        url = host + "/profiles/{}/stats/{}/".format(steam_id, game_id)
        params = {"tab": "achievements", "l": "english"}
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
                    name = name if name != "" else " "
                    achievements.append((unlock_time, name))
            except (AttributeError, ValueError, TypeError):
                logger.exception("Can not parse backend response")
                raise UnknownBackendResponse()

            return achievements

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, parse, text)

    async def get_friends(self, steam_id):
        def parse_response(text):
            def parse_id(profile):
                return profile.attrs["data-steamid"]

            def parse_name(profile):
                return (
                    HTML(html=profile.html)
                    .find(".friend_block_content", first=True)
                    .text.split("\n")[0]
                )

            def parse_avatar(profile):
                avatar_html = HTML(html=profile.html).find(".player_avatar", first=True).html
                return HTML(html=avatar_html).find("img")[0].attrs.get("src")

            def parse_url(profile):
                return (
                    HTML(html=profile.html)
                    .find(".selectable_overlay", first=True)
                    .attrs.get("href")
                )

            try:
                search_results = HTML(html=text).find("#search_results", first=True).html
                return [
                    UserInfo(
                        user_id=parse_id(profile),
                        user_name=parse_name(profile),
                        avatar_url=parse_avatar(profile),
                        profile_url=parse_url(profile),
                    )
                    for profile in HTML(html=search_results).find(".friend_block_v2")
                ]
            except (AttributeError, ValueError, TypeError):
                logger.exception("Can not parse backend response")
                raise UnknownBackendResponse()

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            parse_response,
            await get_text(
                await self._http_client.get(
                    "https://steamcommunity.com/profiles/{}/friends/".format(steam_id),
                    params={"l": "english", "ajax": 1},
                )
            ),
        )

    async def get_game_library_settings_file(self):
        remotestorageapp = await self._http_client.get(
            "https://store.steampowered.com/account/remotestorageapp/?appid=7"
        )
        remotestorageapp_text = await remotestorageapp.text(encoding="utf-8", errors="replace")
        start_index = remotestorageapp_text.find("sharedconfig.vdf")
        if start_index == -1:
            # Fresh user, has no sharedconfig
            return []
        url_start = remotestorageapp_text.find('href="', start_index)
        url_end = remotestorageapp_text.find('">', url_start)
        url = remotestorageapp_text[int(url_start) + len('href="') : int(url_end)]
        sharedconfig = vdf.loads(
            await get_text(await self._http_client.get(url, allow_redirects=True))
        )
        logger.info(f"Sharedconfig file contents {sharedconfig}")
        try:
            apps = sharedconfig["UserRoamingConfigStore"]["Software"]["Valve"]["Steam"]["Apps"]
        except KeyError:
            logger.warning("Cant read users sharedconfig, assuming no tags set")
            return []
        game_settings = []
        for app in apps:
            tags = []
            if "tags" in apps[app]:
                for tag in apps[app]["tags"]:
                    tags.append(apps[app]["tags"][tag])
            hidden = True if "Hidden" in apps[app] and apps[app]["Hidden"] == "1" else False
            game_settings.append({"game_id": app, "tags": tags, "hidden": hidden})
        return game_settings

    async def get_store_popular_tags(self):
        popular_tags = await self._http_client.get(
            "https://store.steampowered.com/tagdata/populartags/english"
        )
        popular_tags = await popular_tags.json()
        return popular_tags

    async def get_game_tags(self, appid):
        try:
            game_info = await self._http_client.get(
                f"https://store.steampowered.com/broadcast/ajaxgetappinfoforcap?appid={appid}&l=english"
            )
            game_info = await game_info.json()
        except (UnknownError, BackendError):
            logger.info(f"No store tags defined for {appid}")
            return {}
        tags = {}

        if "tags" in game_info:
            for tag in game_info["tags"]:
                if "browseable" in tag and tag["browseable"]:
                    tags[tag["tagid"]] = tag["name"]

        return tags

    async def get_game_categories(self, appid):
        try:
            game_info = await self._http_client.get(
                f"https://store.steampowered.com/api/appdetails/?appids={appid}&filters=categories&l=english"
            )
            game_info = await game_info.json()
        except (UnknownError, BackendError):
            logger.info(f"No details defined for {appid}")
            return []
        if (
            str(appid) in game_info
            and "data" in game_info[str(appid)]
            and "categories" in game_info[str(appid)]["data"]
        ):
            return game_info[str(appid)]["data"]["categories"]
        return []

    async def get_owned_ids(self, miniprofile_id):
        url = f"https://store.steampowered.com/dynamicstore/userdata/?id={miniprofile_id}"
        response = await self._http_client.get(url)
        response = await response.json()
        logger.info(f"userdata response {response}")
        return response["rgOwnedApps"]

    async def get_authentication_data(self) -> Tuple[int, str, str]:
        url = "https://steamcommunity.com/chat/clientjstoken"
        response = await self._http_client.get(url)
        try:
            data = await response.json()
            return int(data["steamid"]), data["account_name"], data["token"]
        except (ValueError, KeyError):
            logger.exception("Can not parse backend response")
            raise UnknownBackendResponse()
