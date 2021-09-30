import logging

from galaxy.http import create_client_session, handle_exception


logger = logging.getLogger(__name__)


class HttpClient:
    def __init__(self):
        self._auth_lost_callback = None
        self._session = create_client_session()

    async def close(self):
        await self._session.close()
    
    async def _request(self, method, url, *args, **kwargs):
        with handle_exception():
            return await self._session.request(method, url, *args, **kwargs)
    
    async def get(self, url, *args, **kwargs):
        return await self._request("GET", url, *args, **kwargs)
