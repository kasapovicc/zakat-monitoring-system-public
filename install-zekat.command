#!/bin/bash
#
# Zekat Install Helper
# Double-click this file to clear the macOS quarantine flag and open Zekat.app
#

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_PATH="$SCRIPT_DIR/Zekat.app"

if [ ! -d "$APP_PATH" ]; then
    echo "Zekat.app not found next to this script."
    echo "Make sure install-zekat.command and Zekat.app are in the same folder."
    echo ""
    read -n 1 -s -r -p "Press any key to close..."
    exit 1
fi

echo "Clearing macOS quarantine flag for Zekat.app..."
xattr -cr "$APP_PATH"

echo "Opening Zekat.app..."
open "$APP_PATH"
