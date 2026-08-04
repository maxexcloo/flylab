#!/usr/bin/env bash
set -euo pipefail

: "${SERVICE_PATH:?SERVICE_PATH is required}"
case "$SERVICE_PATH" in
  ""|-*|*[!a-z0-9-]*) exit 1 ;;
esac

render_path=".render/$SERVICE_PATH"
mkdir -p "$render_path"
find "$render_path" -mindepth 1 -delete
rsync -a --exclude '*.tmpl' "$SERVICE_PATH/" "$render_path/"

find "$SERVICE_PATH" -type f -name '*.tmpl' -print |
  while IFS= read -r template; do
    relative_path=${template#"$SERVICE_PATH/"}
    output_path="$render_path/${relative_path%.tmpl}"
    mkdir -p "${output_path%/*}"
    gomplate --file "$template" --out "$output_path"
  done
