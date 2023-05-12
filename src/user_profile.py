import logging
import json
import re

import aiohttp
import xml.etree.ElementTree as ET


logger = logging.getLogger(__name__)


async def get_text(response: aiohttp.ClientResponse) -> str:
    return await response.text(encoding="utf-8", errors="replace")


class UserProfileChecker:
    _BASE_URL = 'https://steamcommunity.com'

    def __init__(self, http_client):
        self._http_client = http_client

    async def check_is_public_by_custom_url(self, username) -> bool:
        url = self._BASE_URL + f'/id/{username}/games/?xml=1'
        return await self._verify_is_public(url)

    async def check_is_public_by_steam_id(self, steam_id) -> bool:
        if not steam_id:
            raise ValueError(f"Incorrect Steam64 ID value: {steam_id}")
        url = self._BASE_URL + f'/profiles/{steam_id}/games/?xml=1'
        return await self._verify_is_public(url)

    async def _verify_is_public(self, url: str) -> bool:
        text = await get_text(await self._http_client.get(url))
        root = ET.fromstring(text)

        error_elm = root.find('./error')
        error_txt = getattr(error_elm, 'text', None)

        if error_txt:
            logger.error(f'Error from Steam: {error_txt}')
            if error_txt == 'The specified profile could not be found.':
                raise ProfileDoesNotExist
            if error_txt == 'This profile is private.':
                raise ProfileIsNotPublic
            raise ParseError

        game_elm = root.find('./games/game')
        if not game_elm:
            logger.error(f'Unable to find any game element')
            raise NotPublicGameDetailsOrUserHasNoGames
        
        return True


class ProfileDoesNotExist(Exception):
    pass


class ProfileIsNotPublic(Exception):
    pass


class ParseError(Exception):
    pass


class NotPublicGameDetailsOrUserHasNoGames(Exception):
    pass
