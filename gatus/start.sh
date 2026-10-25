#!/bin/sh
set -eu
export PATH="/app:$PATH"
env -u TAILSCALE_OAUTH_CLIENT_SECRET tailscaled --socket=/var/run/tailscale/tailscaled.sock --state=/var/lib/tailscale/tailscaled.state &
timeout 15 sh -c 'until [ -S /var/run/tailscale/tailscaled.sock ]; do sleep 0.1; done'
printf '%s' "${TAILSCALE_OAUTH_CLIENT_SECRET}?ephemeral=true&preauthorized=true" |
  tailscale up --accept-dns=false --accept-routes=false --advertise-tags=tag:fly --auth-key=file:/dev/stdin --hostname=gatus --timeout=60s
unset TAILSCALE_OAUTH_CLIENT_SECRET
env GATUS_CONFIG_PATH=/app/config gatus &
gatus_pid=$!
# Logging out removes the ephemeral node at once, so the next start can reuse the hostname.
trap 'tailscale logout; kill "$gatus_pid"' INT TERM
wait "$gatus_pid" || wait "$gatus_pid"
