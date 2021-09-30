# Steam Integration

GOG Galaxy 2.0 Community integration for Steam.

## Installation

*The latest release should be available for download via the "Connect" button in Galaxy*

### To install a custom build:
* make sure Galaxy is closed
* remove the currently installed plugin directory (if present), usually<br>
`%localappdata%\GOG.com\Galaxy\plugins\installed\steam_ca27391f-2675-49b1-92c0-896d43afa4f8`
* create a new folder under a name of your choice (the name doesn't matter) at the following path:<br>
`%localappdata%\GOG.com\Galaxy\plugins\installed\`
* copy the custom build files to the newly created folder

If the latest version available on Github is newer than the version specified in the `manifest.json` file in the custom build, Galaxy will download the newer version and replace the files. To prevent this from happening, you can manually set the version in `manifest.json` to a significantly higher value (e.g. `9.9`).

## Configuration of the backend operation mode

The plugin supports different data collectors, called `backends`.

Currently supported `backends` are:
1. `Steam Network`
    - uses internal Steam protocols 
    - supports library, game times, achievements, importing tags, friends presence
2. `Public Profiles`
    - works without providing user credentials
    - requires steamcommunity.com user's profile to be set as public with access at least for games library
    - supports library, game times, achievements, importing tags

NOTE: Data imported by different `backends` may differ due to both Steam side inconsistencies and limitations of specific `backend` implementation.

NOTE: interaction with local games and local Steam client is the same for all `backends`.

The behavior is configurable using a `config file`.

### Config file location

- Windows:
`%localappdata%\GOG.com\Galaxy\plugins\installed\steam_plugin_config.ini`

- MacOS:
`~/Library/Application Support/GOG.com/Galaxy/plugins/installed/steam_plugin_config.ini`

### Default behavior

Initial `backend` (with the login window) is set to use `Steam Network` and switches to `Public Profiles` automatically when stored token become invalid (for the main reason see #74).

## Credits

Based on work and research done by others:
* https://github.com/prncc/steam-scraper
* https://github.com/rhaarm/steam-scraper
* https://github.com/mulhod/steam_reviews
* https://github.com/summersb92/aeolipile
* https://github.com/rcpoison/steam-scraper
* https://github.com/chmccc/steam-scraper
