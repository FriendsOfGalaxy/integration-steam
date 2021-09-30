import asyncio
import base64
import logging as log


class UserInfoCache:
    def __init__(self):
        self._steam_id = None
        self._account_id = None
        self._account_username = None
        self._persona_name = None
        self._token = None
        self._two_step = None
        self._sentry = b''
        self._changed = False
        self.old_flow = False
        self.initialized = asyncio.Event()

    def _check_initialized(self):
        if self._steam_id and self._account_id and self._account_username and self._persona_name and self._token:
            log.info("User info cache initialized")
            self.initialized.set()
            self._changed = True

    def to_dict(self):
        creds = {'steam_id': base64.b64encode(str(self._steam_id).encode('utf-8')).decode('utf-8'),
                 'account_id': base64.b64encode(str(self._account_id).encode('utf-8')).decode('utf-8'),
                 'token': base64.b64encode(str(self._token).encode('utf-8')).decode('utf-8'),
                 'account_username': base64.b64encode(str(self._account_username).encode('utf-8')).decode('utf-8'),
                 'persona_name': base64.b64encode(str(self._persona_name).encode('utf-8')).decode('utf-8'),
                 'sentry': base64.b64encode(self._sentry).decode('utf-8')}
        return creds

    def from_dict(self, dict):
        for key in dict.keys():
            if dict[key]:
                log.info(f"Loaded {key} from stored credentials")

        if 'steam_id' in dict:
            self._steam_id = int(base64.b64decode(dict['steam_id']).decode('utf-8'))

        if 'account_id' in dict:
            self._account_id = int(base64.b64decode(dict['account_id']).decode('utf-8'))

        if 'account_username' in dict:
            self._account_username = base64.b64decode(dict['account_username']).decode('utf-8')

        if 'persona_name' in dict:
            self._persona_name = base64.b64decode(dict['persona_name']).decode('utf-8')

        if 'token' in dict:
            self._token = base64.b64decode(dict['token']).decode('utf-8')

        if 'sentry' in dict:
            self._sentry = base64.b64decode(dict['sentry'])

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
    def account_id(self):
        return self._account_id

    @account_id.setter
    def account_id(self, val):
        if self._account_id != val and self.initialized.is_set():
            self._changed = True
        self._account_id = val
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
    def token(self):
        return self._token

    @token.setter
    def token(self, val):
        if self._token != val and self.initialized.is_set():
            self._changed = True
        self._token = val
        if not self.initialized.is_set():
            self._check_initialized()

    @property
    def two_step(self):
        return self._two_step

    @two_step.setter
    def two_step(self, val):
        if self._two_step != val and self.initialized.is_set():
            self._changed = True
        self._two_step = val
        if not self.initialized.is_set():
            self._check_initialized()

    @property
    def sentry(self):
        return self._sentry

    @sentry.setter
    def sentry(self, val):
        if self._sentry != val and self.initialized.is_set():
            self._changed = True
        self._sentry = val
        if not self.initialized.is_set():
            self._check_initialized()
