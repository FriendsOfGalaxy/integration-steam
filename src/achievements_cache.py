from dataclasses import dataclass, asdict
from typing import Optional

from galaxy.api.types import Achievement

from cache import Cache


@dataclass
class Fingerprint:
    time_played: int
    last_played_time: Optional[int]


def as_dict(cache: Cache) -> dict:
    dict_ = {}
    for key, achievements, fingerprint in cache:
        achievements = [asdict(achievement) for achievement in achievements]
        dict_[key] = {
            "achievements": achievements,
            "fingerprint": asdict(fingerprint)
        }
    return dict_


def from_dict(dict_: dict) -> Cache:
    cache = Cache()
    for key, value in dict_.items():
        try:
            achievements = value["achievements"]
            achievements = [Achievement(**achievement) for achievement in achievements]
            fingerprint = value["fingerprint"]
            fingerprint = Fingerprint(**fingerprint)
        except (KeyError, TypeError, AssertionError) as error:
            raise ValueError("Failed to deserialize cache from dictionary") from error
        cache.update(key, achievements, fingerprint)
    return cache
