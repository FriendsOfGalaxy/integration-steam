from typing import Optional, List, Tuple, Dict
from .enums import TwoFactorMethod


class AuthenticationCache:
    """ Cache designed to carry authentication-related information between the websocket and interface code. 

    This 'cache' is not designed to persist in any manner. it's simply a data-storage device. 
    """
    def __init__(self):
       #pairs of Two Factor methods and their any related message if provided. This is not a dict because we prioritize different methods and therefore a sorted list of tuples makes more sense than a dict. 
        self._two_factor_allowed_methods : Optional[List[Tuple[TwoFactorMethod, str]]]
        self._error_message: Optional[str] = None #used to display specific errors. Things like "passcode expired" or "password incorrect" or "username does not exist"

    @property
    def two_factor_allowed_methods(self):
        return self._two_factor_allowed_methods

    @property
    def error_message(self):
        return self._error_message

    @error_message.setter
    def error_message(self, val):
        self._error_message = val

    #provides a priority for our list based on two factor method
    def _auth_priority(self, methodPair : Tuple[TwoFactorMethod, str]) -> int:
        method, _ = methodPair
        if (method == TwoFactorMethod.Unknown):
            return 0
        elif (method == TwoFactorMethod.Nothing):
            return 1
        elif (method == TwoFactorMethod.EmailCode):
            return 2
        elif (method == TwoFactorMethod.PhoneCode):
            return 3
        elif (method == TwoFactorMethod.PhoneConfirm):
            return 4
        else:
            return -1

    def update_authentication_cache(self, two_factor_dict: Dict[TwoFactorMethod, str], error_message: str):
        self._error_message = error_message
        self._two_factor_allowed_methods = []
        for (key, value) in two_factor_dict.items():
            self._two_factor_allowed_methods.append((key, value))

        self._two_factor_allowed_methods.sort(key=self._auth_priority, reverse=True)


