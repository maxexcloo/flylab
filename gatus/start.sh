#!/bin/sh
set -eu
export PATH="/app:$PATH"
tailscaled --socket=/var/run/tailscale/tailscaled.sock --state=/var/lib/tailscale/tailscaled.state &
tailscale up --accept-dns=false --accept-routes=false --authkey="${TAILSCALE_AUTH_KEY}" --hostname=gatus
exec env GATUS_CONFIG_PATH=/app/config gatus
