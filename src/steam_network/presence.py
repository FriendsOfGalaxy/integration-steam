from galaxy.api.consts import PresenceState
from galaxy.api.types import UserPresence

from .protocol.consts import EPersonaState
from .protocol.steam_types import ProtoUserInfo

import re
import logging
import asyncio
logger = logging.getLogger(__name__)


def _translate_string(game_id, string, translations_cache):
    token_list = translations_cache[int(game_id)]
    for token in token_list.tokens:
        if token.name.lower() == string.lower():
            return token.value


async def _translate_presence(user_info, status : str , token_list):
                    replaced = True
                    max_depth = 10
                    current_depth = 0
                    while replaced:
                        if current_depth >= max_depth:
                            logger.info(f"Unable to resolve rich presence translation for {user_info}")
                            return None
                        current_depth += 1
                        replaced = False

                        params = user_info.rich_presence.keys()
                        for param in params:
                            if "%"+param.lower()+"%" in status.lower():
                                param_replace = re.compile(re.escape("%"+param+"%"), re.IGNORECASE)
                                status = param_replace.sub(user_info.rich_presence.get(param), status)
                                replaced = True

                        for token in token_list.tokens:
                            if re.findall(rf'{token.name.lower()}(\s|#|%|\Z)', status.lower()):
                                token_replace = re.compile(rf'{re.escape(token.name)}(\s|#|%|\Z)', re.IGNORECASE)
                                status = token_replace.sub(token.value, status)
                                replaced = True
                                break

                        status = status.replace("{"," ")
                        status = status.replace("}"," ")

                    return status


async def presence_from_user_info(user_info: ProtoUserInfo, translations_cache: dict) -> UserPresence:
    if user_info.state == EPersonaState.Online:
        state = PresenceState.Online
    elif user_info.state == EPersonaState.Snooze:
        # In game afk, sitting in the main menu etc. Steam chat and others show this as online/in-game
        state = PresenceState.Online
    elif user_info.state == EPersonaState.Offline:
        state = PresenceState.Offline
    elif user_info.state == EPersonaState.Away:
        state = PresenceState.Away
    elif user_info.state == EPersonaState.Busy:
        state = PresenceState.Away
    else:
        state = PresenceState.Unknown

    game_id = str(user_info.game_id) if user_info.game_id is not None and user_info.game_id != 0 else None

    game_title = user_info.game_name if user_info.game_name is not None and user_info.game_name else None

    status = None
    if user_info.rich_presence is not None:
        logger.info(f"Attempting to resolve rich presence from {user_info}")
        check_for_params = r"%.*%"
        status = user_info.rich_presence.get("steam_display")
        if not status:
            status = user_info.rich_presence.get("status")
        if status:
            try:
                if int(game_id) in translations_cache and translations_cache[int(game_id)]:
                    try:
                        status = await asyncio.wait_for(_translate_presence(user_info,status, translations_cache[int(game_id)]), timeout=1)
                    except asyncio.TimeoutError:
                        logger.info(f"Timed out translating presence {user_info.rich_presence} using {translations_cache[int(game_id)]}")
                        status = None
                elif "#" in status or re.findall(check_for_params, status):
                    logger.info(f"Skipping not simple rich presence status {status}")
                    status = None
            except Exception as e:
                logger.info(f"Unable to translate rich presence {status} due to  {repr(e)}")
                status = None

    return UserPresence(
        presence_state=state,
        game_id=game_id,
        game_title=game_title,
        in_game_status=status
    )
