from typing import Set


WITCHER_3_DLCS_APP_IDS = ("355880", "378648", "378649")
WITCHER_3_GOTY_APP_ID = "499450"
WITCHER_3_GOTY_TITLE = "The Witcher 3: Wild Hunt - Game of the Year Edition"


def does_witcher_3_dlcs_set_resolve_to_GOTY(owned_dlc_app_ids: Set[int]) -> bool:
    W3_EXPANSION_PASS = "355880"
    W3_DLCS_GOTY_COMPONENTS = {"378648", "378649"}
    return W3_EXPANSION_PASS in owned_dlc_app_ids \
        or len(W3_DLCS_GOTY_COMPONENTS - owned_dlc_app_ids) == 0
