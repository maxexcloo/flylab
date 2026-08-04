#!/usr/bin/env bash
set -euo pipefail

: "${APP:?APP is required}"
case "$APP" in
  ""|-*|*[!a-z0-9-]*) exit 1 ;;
esac

if flyctl apps info "$APP" >/dev/null 2>&1; then
  flyctl apps destroy "$APP" --yes
else
  echo "$APP does not exist"
fi
