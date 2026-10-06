#!/bin/sh
set -eu
umask 077
if [ -f /run/secrets/bridge_password ]; then
    CARBONATE_BRIDGE_PASSWORD=$(cat /run/secrets/bridge_password)
    export CARBONATE_BRIDGE_PASSWORD
fi
exec "$@"
