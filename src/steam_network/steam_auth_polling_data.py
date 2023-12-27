from .enums import UserActionRequired, TwoFactorMethod

from typing import Dict

class SteamPollingData:
    """ Contains the data needed to poll the steam api for login success.
   
    For the most part, this data is immutable, but the client id can update if two-factor authentication times out. 
    """
    def __init__(self, cid: int, sid: int, rid:bytes, intv:float, conf: Dict[TwoFactorMethod, str], eem: str):
        self._client_id : int = cid     #the id assigned to us.
        self._steam_id : int = sid       #the id of the user that signed in
        self._request_id : bytes = rid  #unique request id. needed for the polling function.
        self._interval : float = intv   #interval to poll on.

        #list of pairs of two factor methods, which are used to determine which methods the user will allow, and a related message (something like "we sent a message to q******@g****.com")
        self._allowed_confirmations : Dict[TwoFactorMethod, str] = conf

        self._extended_error_message : str = eem #used for errors. 

    @property
    def client_id(self):
        return self._client_id

    @client_id.setter
    def client_id(self, arg:int):
        self._client_id = arg

    @property
    def steam_id(self):
        return self._steam_id

    @property
    def request_id(self):
        return self._request_id

    @property
    def interval(self):
        return self._interval

    @property
    def allowed_confirmations(self):
        return self._allowed_confirmations.copy()

    @property
    def extended_error_message(self):
        return self._extended_error_message

    def has_valid_confirmation_method(self):
        #if any value in allowed confirmations does not equal unknown, return true. else return false.
        return any(c != TwoFactorMethod.Unknown for c in self._allowed_confirmations)
