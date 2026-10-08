#!/bin/sh
set -eu
export PATH="/app:$PATH"
tailscaled --socket=/var/run/tailscale/tailscaled.sock --state=/var/lib/tailscale/tailscaled.state &
timeout 15 sh -c 'until [ -S /var/run/tailscale/tailscaled.sock ]; do sleep 0.1; done'
tailscale up --timeout=60s --accept-dns=false --accept-routes=false --authkey="${TAILSCALE_AUTH_KEY}" --hostname=gatus
exec env GATUS_CONFIG_PATH=/app/config gatus
