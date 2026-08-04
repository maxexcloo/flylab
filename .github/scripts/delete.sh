#!/usr/bin/env bash
set -euo pipefail

if flyctl apps info "$APP" >/dev/null 2>&1; then
  flyctl apps destroy "$APP" --yes
else
  echo "$APP does not exist"
fi
