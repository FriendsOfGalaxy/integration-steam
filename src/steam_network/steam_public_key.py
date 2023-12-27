from typing import NamedTuple
from rsa import PublicKey

class SteamPublicKey(NamedTuple):
    rsa_public_key: PublicKey
    timestamp: int