#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

exec java -jar "$SCRIPT_DIR/oculixide-4.0.0-macos.jar" \
    -c -r "$SCRIPT_DIR/auto.py" "$@"
