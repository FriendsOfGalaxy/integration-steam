import struct
from dataclasses import dataclass, fields
from typing import Dict, Optional

from .consts import EPersonaState


@dataclass
class SteamId:
    """
        unsigned ID : 32;
        unsigned instance : 20;
        unsigned type : 4;
        unsigned universe : 8;
    """
    id_: int
    instance: int
    type_: int
    universe: int
    
    @staticmethod
    def parse(steam_id: int):
        data = struct.pack("<Q", steam_id)
        id_, rest = struct.unpack("<II", data)
        instance = rest & 0xFFFFF
        type_ = (rest >> 20) & 0xF
        universe = rest >> 24
        return SteamId(id_, instance, type_, universe)


@dataclass
class ProtoUserInfo:
    name: Optional[str] = None
    avatar_hash: Optional[str] = None
    state: Optional[EPersonaState] = None
    game_id: Optional[int] = None
    game_name: Optional[str] = None
    rich_presence: Optional[Dict[str, str]] = None

    def update(self, other):
        updated = False
        for field in fields(self):
            new_value = getattr(other, field.name)
            old_value = getattr(self, field.name)
            if new_value is not None:
                if new_value != old_value:
                    setattr(self, field.name, new_value)
                    updated = True
        return updated

@dataclass
class AppInfo:
    appid: Optional[int] = None
    buffer: Optional[str] = None  # Text vdf

@dataclass
class PackageInfo:
    appid: Optional[int] = None
    buffer: Optional[str] = None  # Binary vdf
