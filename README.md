# Steam Integration

GOG Galaxy 2.0 Community integration for Steam.

## Installation

*Latest release should be available directly from Galaxy*

#### For custom build
- close Galaxy
- remove previously installed plugin folder (if any), usually<br>
`%localappdata%\GOG.com\Galaxy\plugins\installed\steam_ca27391f-2675-49b1-92c0-896d43afa4f8`
- create a folder of any name at the following path and copy the custom build to it:<br>
`%localappdata%\GOG.com\Galaxy\plugins\installed\`

Once the latest version on Github is newer than the version provided in `manifest.json` in the custom build, Galaxy will download the newer version and replace the custom build. To prevent this, you can manually set the version in `manifest.json` to something significantly bigger like `9.9`.

## Credits

Based on work and research done by others:
* https://github.com/prncc/steam-scraper
* https://github.com/rhaarm/steam-scraper
* https://github.com/mulhod/steam_reviews
* https://github.com/summersb92/aeolipile
* https://github.com/rcpoison/steam-scraper
* https://github.com/chmccc/steam-scraper
