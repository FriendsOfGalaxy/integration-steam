import logging
from typing import List

from galaxy.api.errors import UnknownBackendResponse

from http_client import HttpClient


logger = logging.getLogger(__name__)


class SteamHttpClient:
    def __init__(self, http_client: HttpClient):
        self._http_client = http_client

    async def get_servers(self, cell_id) -> List[str]:
        url = f"http://api.steampowered.com/ISteamDirectory/GetCMList/v1/?cellid={cell_id}"
        response = await self._http_client.get(url)
        try:
            data = await response.json()
            return data['response']['serverlist_websockets']
        except (ValueError, KeyError) :
            logger.exception("Can not parse backend response")
            raise UnknownBackendResponse()
