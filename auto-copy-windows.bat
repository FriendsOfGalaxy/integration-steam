@echo off
setlocal enabledelayedexpansion
cd /d %~dp0

set "PLUGIN_PATH=%localappdata%\GOG.com\Galaxy\plugins\installed\steam_ca27391f-2675-49b1-92c0-896d43afa4f8"

rmdir /S /Q -rf "%PLUGIN_PATH%"
mkdir "%PLUGIN_PATH%"

set zip_file=%~dp0windows.zip
echo Extracting %zip_file%
powershell Expand-Archive '%zip_file%' -DestinationPath '%PLUGIN_PATH%'