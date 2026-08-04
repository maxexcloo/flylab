#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${APP:-}" ]]; then
  echo "APP is required" >&2
  exit 1
fi
if [[ ! "$APP" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]]; then
  echo "Invalid Fly app name: $APP" >&2
  exit 1
fi

if flyctl apps info "$APP" >/dev/null 2>&1; then
  flyctl apps destroy "$APP" --yes
else
  echo "$APP does not exist"
fi
