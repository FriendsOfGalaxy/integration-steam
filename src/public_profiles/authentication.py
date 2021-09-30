import pathlib

from galaxy.api.types import NextStep
import yarl


DIRNAME = yarl.URL(
    pathlib.Path(__file__).parent.as_uri()
)


class StartUri():
    __INDEX = DIRNAME / 'custom_login' / 'index.html'  

    LOGIN =                    __INDEX % {'view': 'login'}
    LOGIN_FAILED =             __INDEX % {'view': 'login', 'errored': 'true'}
    PROFILE_DOES_NOT_EXIST =   __INDEX % {'view': 'login', 'profile_does_not_exist': 'true'}
    PROFILE_IS_NOT_PUBLIC =    __INDEX % {'view': 'login', 'profile_is_not_public': 'true'}


def next_step_response(start_uri):
    return NextStep("web_session", {
        "window_title": "Login to Steam",
        "window_width": 500,
        "window_height": 460,
        "start_uri": str(start_uri),
        "end_uri_regex": '.*(login_finished|open_in_default_browser).*'
    })
