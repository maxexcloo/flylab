#!/bin/sh
set -eu
export PATH="/app:$PATH"
tailscaled --socket=/var/run/tailscale/tailscaled.sock --state=/var/lib/tailscale/tailscaled.state &
timeout 15 sh -c 'until [ -S /var/run/tailscale/tailscaled.sock ]; do sleep 0.1; done'
printf '%s' "${TAILSCALE_OAUTH_CLIENT_SECRET}?ephemeral=false&preauthorized=true" |
  tailscale up --accept-dns=false --accept-routes=false --advertise-tags=tag:fly --auth-key=file:/dev/stdin --hostname=gatus --timeout=60s
unset TAILSCALE_OAUTH_CLIENT_SECRET
exec env GATUS_CONFIG_PATH=/app/config gatus
