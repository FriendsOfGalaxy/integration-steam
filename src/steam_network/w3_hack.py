from typing import Set


WITCHER_3_DLCS_APP_IDS = ("355880", "378648", "378649")
WITCHER_3_GOTY_APP_ID = "499450"
WITCHER_3_GOTY_TITLE = "The Witcher 3: Wild Hunt - Game of the Year Edition"


def does_witcher_3_dlcs_set_resolve_to_GOTY(owned_dlc_app_ids: Set[str]) -> bool:
    w3_expansion_pass = "355880"
    w3_dlcs_goty_components = {"378648", "378649"}
    return w3_expansion_pass in owned_dlc_app_ids \
        or len(w3_dlcs_goty_components - owned_dlc_app_ids) == 0
