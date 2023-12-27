import asyncio
import base64
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)

class UserInfoCache:
    def __init__(self):
        self._steam_id: Optional[int] = None #unique id Steam assigns to the user
        self._account_username: Optional[str] = None #user name for the steam account.
        self._persona_name: Optional[str] = None #friendly name the user goes by in their display. It's what we use when saying "logged in" in the integration page.
        #Note: The tokens below are strings, but they are formatted as JSON Web Tokens (JWT). We can parse them to determine when the refresh token will expire.
        self._refresh_token : Optional[str] = None #persistent token. Used to log in, despite the fact that we should use an access token. weird quirk in how steam does things.
        self._access_token : Optional[str] = None #session login token. Largely useless. May be useful in future if steam fixes their login to use an access token instead of refresh token. 

        self._changed = False
        
        self.initialized = asyncio.Event()

    def _check_initialized(self):
        if self.is_initialized():
            logger.info("User info cache initialized")
            self.initialized.set()
            self._changed = True

    def is_initialized(self) -> bool:
        #if testing and you want to disable login from saved token, you can return false here. 

        return all([self._steam_id is not None, self._account_username, self._persona_name, self._refresh_token])


    def to_dict(self):
        creds = {}
        if self.is_initialized():
            creds = {
                'steam_id': base64.b64encode(str(self._steam_id).encode('utf-8')).decode('utf-8'),
                'refresh_token': base64.b64encode(self._refresh_token.encode('utf-8')).decode('utf-8'),
                'account_username': base64.b64encode(self._account_username.encode('utf-8')).decode('utf-8'),
                'persona_name': base64.b64encode(self._persona_name.encode('utf-8')).decode('utf-8'),
            }
        return creds

    def from_dict(self, lookup: Dict[str, str]):
        for key, val in lookup.items():
            if val:
                logger.info(f"Loaded {key} from stored credentials")

        item = lookup.get('steam_id')
        if item is not None:
            self._steam_id = int(base64.b64decode(item).decode('utf-8'))

        item = lookup.get('account_username')
        if item is not None:
            self._account_username = base64.b64decode(item).decode('utf-8')


        item = lookup.get('persona_name')
        if item is not None:
            self._persona_name = base64.b64decode(item).decode('utf-8')

        item = lookup.get('refresh_token')
        if item is not None:
            self._refresh_token = base64.b64decode(item).decode('utf-8')

    @property
    def changed(self):
        if self._changed:
            self._changed = False
            return True
        return False

    @property
    def steam_id(self):
        return self._steam_id

    @steam_id.setter
    def steam_id(self, val):
        if self._steam_id != val and self.initialized.is_set():
            self._changed = True
        self._steam_id = val
        if not self.initialized.is_set():
            self._check_initialized()

    @property
    def account_username(self):
        return self._account_username

    @account_username.setter
    def account_username(self, val):
        if self._account_username != val and self.initialized.is_set():
            self._changed = True
        self._account_username = val
        if not self.initialized.is_set():
            self._check_initialized()

    @property
    def persona_name(self):
        return self._persona_name

    @persona_name.setter
    def persona_name(self, val):
        if self._persona_name != val and self.initialized.is_set():
            self._changed = True
        self._persona_name = val
        if not self.initialized.is_set():
            self._check_initialized()

    @property
    def access_token(self):
        return self._access_token

    @access_token.setter
    def access_token(self, val):
        if self._access_token != val and self.initialized.is_set():
            self._changed = True
        self._access_token = val
        if not self.initialized.is_set():
            self._check_initialized()

    @property
    def refresh_token(self):
        return self._refresh_token

    @refresh_token.setter
    def refresh_token(self, val):
        if self._refresh_token != val and self.initialized.is_set():
            self._changed = True
        self._refresh_token = val
        if not self.initialized.is_set():
            self._check_initialized()

    def Clear(self):
        self._refresh_token = None
        self._steam_id = None 
        self._account_username = None 
        self._persona_name = None 
        self._access_token  = None 
