#!/bin/sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MAC_ZIP="$SCRIPT_DIR/mac.zip"
PLUGIN_PATH="$HOME/Library/Application Support/GOG.com/Galaxy/plugins/installed/steam_ca27391f-2675-49b1-92c0-896d43afa4f8"

rm -rf "$PLUGIN_PATH"
mkdir -p "$PLUGIN_PATH"
unzip "$MAC_ZIP" -d "$PLUGIN_PATH"
find "$PLUGIN_PATH" -name "*.so" -exec xattr -c {} \;
