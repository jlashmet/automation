#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export AUTOMATION_DIR="$SCRIPT_DIR"

# Oculix runs inside one JVM. Give the IDE/Jython coordinator enough headroom for
# long-running browser automation instead of relying on the JVM's automatic heap sizing.
# Override either value when needed, for example:
#   OCULIX_MAX_HEAP=12g ./run.sh
OCULIX_MIN_HEAP=${OCULIX_MIN_HEAP:-1g}
OCULIX_MAX_HEAP=${OCULIX_MAX_HEAP:-8g}

# Run the Oculix-native .sikuli bundle. Plain .py IDE support is still incomplete in
# Oculix and can fail before an active editor content object exists.
exec java \
    "-Xms${OCULIX_MIN_HEAP}" \
    "-Xmx${OCULIX_MAX_HEAP}" \
    -jar "$SCRIPT_DIR/oculixide-4.0.0-macos.jar" \
    -c -r "$SCRIPT_DIR/auto.sikuli" "$@"
