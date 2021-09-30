from unittest.mock import mock_open
from textwrap import dedent

import pytest

from backend_configuration import (
    BackendMode,
    BackendConfiguration,
    USER_CONFIG_LOCATION,
    ConfigParseError,
)


pytestmark = pytest.mark.asyncio


HEADER_END_MARK = "; === end of generated part ==="


@pytest.fixture
def default_initial_backend(register_mock_backend):
    return register_mock_backend(BackendMode.SteamNetwork)


# test fixtures


async def test_patch_config_location_fixture_file_existence(patch_config_location):
    user_config = patch_config_location()
    assert not user_config.exists(), "patched config file shouldn't exists yet"
    user_config.write_text("")
    assert user_config.exists()


async def test_register_mock_backend_fixture_produces_not_called_backend(
    register_mock_backend,
):
    steam_network_backend_cls = register_mock_backend(BackendMode.SteamNetwork)
    steam_network_backend_cls.assert_not_called()


# unittests for plugin behavior


async def test_reading_proper_config_file(create_plugin, mocker):
    open_mock = mocker.patch("builtins.open", mock_open())
    create_plugin()
    args, _ = open_mock.call_args
    assert USER_CONFIG_LOCATION in args


async def test_no_config__use_defaults(
    create_plugin, default_initial_backend, patch_config_location
):
    patch_config_location()

    plugin = create_plugin()
    plugin.handshake_complete()

    default_initial_backend.assert_called()


async def test_empty_config__use_defaults(create_plugin, default_initial_backend, mocker):
    mocker.patch("builtins.open", mock_open(read_data=""))

    plugin = create_plugin()
    plugin.handshake_complete()

    default_initial_backend.assert_called_once()


async def test_no_config__dump_an_empty_one(create_plugin, patch_config_location):
    user_config = patch_config_location()

    plugin = create_plugin()
    plugin.handshake_complete()

    with open(user_config) as f:
        for line in f.readlines():
            assert (
                line.isspace() or line.startswith(";") or line.startswith("#")
            ), "config should contain only comments, but there is: [{}]".format(line)


@pytest.mark.parametrize(
    "initial_header, initial_actual_content",
    [
        pytest.param(
            "", "[BackendMode]\ninitial=public_profiles", id="user content with no header"
        ),
        pytest.param(
            "",
            "[BackendMode]\ninitial=public_profiles\n",
            id="user content with no header and new line at the end",
        ),
        pytest.param(
            "",
            ";user comment\n[BackendMode]\ninitial=public_profiles",
            id="user content started with a comment with no header",
        ),
        pytest.param(
            HEADER_END_MARK[:-1],  # without newline character
            ";user comment \n[BackendMode]\ninitial=public_profiles",
            id="user content started with a comment with a minimal header",
        ),
        pytest.param(
            "",
            dedent("""
                [BackendMode]
                initial = public_profiles
            """
            ),
            id="user content with no header",
        ),
        pytest.param(
            dedent(
                f"""; HEADER
                ; INSTRUCTIONS
                {HEADER_END_MARK}"""
            ),
            "",
            id="empty user content with a header (deafult use case)",
        ),
        pytest.param(
            dedent(
                f"""; CUSTOM HEADER GOES HERE
                ;
                {HEADER_END_MARK}"""
            ),
            dedent(
                """; user comment 1
                [BackendMode]     
                ; user comment 2
                initial = public_profiles
            """
            ),
            id="user config with mutliple comments with a header",
        ),
        pytest.param(
            dedent(
                f"""[BackendMode]
                initial = public_profiles
                {HEADER_END_MARK}"""
            ),
            "",
            id="content from before header should be overriden"
        )
    ],
)
async def test_do_not_override_existing_config_content(
    create_plugin, patch_config_location, initial_header, initial_actual_content
):
    user_config = patch_config_location()
    initial_content = initial_header + initial_actual_content
    user_config.write_text(initial_content)

    plugin = create_plugin()
    plugin.handshake_complete()

    assert initial_actual_content in open(user_config).read()
    # load config again to make sure its content is not broken (passes validation)
    plugin = create_plugin()


async def test_config_not_accesible_for_read_and_write(
    create_plugin, mocker, default_initial_backend
):
    """Should load defaults and do not break"""
    mocker.patch("builtins.open").side_effect = OSError

    plugin = create_plugin()
    plugin.handshake_complete()

    default_initial_backend.assert_called_once()


@pytest.mark.parametrize(
    "expected_mode, config_content",
    [
        (BackendMode.PublicProfiles, "[BackendMode]\n initial=public_profiles"),
        (BackendMode.SteamNetwork, "[BackendMode]\n initial=steam_network"),
    ],
)
async def test_load_backend_initial_mode(
    create_plugin,
    register_mock_backend,
    mocker,
    config_content,
    expected_mode,
):
    backend_class = register_mock_backend(expected_mode)
    mocker.patch("builtins.open", mock_open(read_data=config_content))

    plugin = create_plugin()
    plugin.handshake_complete()

    backend_class.assert_called_once()


@pytest.mark.parametrize(
    "content",
    [
        "invalid string",
        "[]",
        "{}",
        "[BackendMode]\n initial=invalid_option",
        "[BackendMode]\n initial=",
        "[BackendMode]\n initial=steam_network\n fallback=invalid_value",
        "[BackendMode]\n initial=steam_network \n fallback=",
        "[UnknownSection]\n initial=public_profiles",
    ],
)
async def test_invalid_config(create_plugin, mocker, content):
    """Fail fast with a plugin crash to give quick feedback for a user."""
    mocker.patch("builtins.open", mock_open(read_data=content))
    with pytest.raises(ConfigParseError):
        create_plugin()


@pytest.mark.parametrize(
    "content",
    [
        "",
        "[BackendMode]",
    ],
)
async def test_valid_config(create_plugin, mocker, content):
    """
    Checks for config content data that is strange, but technically valid in the current implementation.
    Validator could be stricter, but for now there is no need to implement that.
    Added for documenting purposes.
    """
    mocker.patch("builtins.open", mock_open(read_data=content))
    try:
        create_plugin()
    except ConfigParseError as e:
        pytest.fail(f"{e.__class__} was not raised previously")


# unittests for BackendConfiguration
# e.i. the rest config related behaviors that couldn't be easily tested
# by inspecting public SteamPlugin interface
# (without depending on other behaviors like backend switching)


@pytest.mark.parametrize(
    "expected_mode, config_content",
    [
        (BackendMode.PublicProfiles, "[BackendMode]\n fallback=public_profiles"),
        (BackendMode.SteamNetwork, "[BackendMode]\n fallback=steam_network"),
        pytest.param(None, "[BackendMode]\n fallback=none", id="disabled fallback"),
    ],
)
async def test_load_backend_fallback_mode(tmp_path, config_content, expected_mode):
    cfg_path = tmp_path / "config.ini"
    cfg_path.write_text(config_content)

    config = BackendConfiguration()
    config.read_strict(cfg_path)

    assert config.fallback_mode == expected_mode


@pytest.mark.parametrize(
    "initial_mode, fallback_mode, config_content",
    [
        pytest.param(
            BackendMode.SteamNetwork,
            BackendMode.PublicProfiles,
            "[BackendMode]\n fallback=public_profiles\n initial=steam_network",
            id="steam_network with public_profiles as a fallback",
        ),
        pytest.param(
            BackendMode.PublicProfiles,
            None,
            "[BackendMode]\n fallback=none \n initial=public_profiles",
            id="hardcoded to use only public profiles",
        ),
    ],
)
async def test_backend_both_modes(
    tmp_path,
    config_content,
    initial_mode,
    fallback_mode,
):
    cfg_path = tmp_path / "config.ini"
    cfg_path.write_text(config_content)

    config = BackendConfiguration()
    config.read_strict(cfg_path)

    assert config.initial_mode == initial_mode
    assert config.fallback_mode == fallback_mode
