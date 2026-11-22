#!/bin/bash
# Prepare the asset link, then run the container command.
# Do not create sites, install apps, migrate, or build assets.
set -euo pipefail

bench="/home/frappe/frappe-bench"
assets_path="${bench}/sites/assets"
baked_path="${bench}/assets"

mkdir -p "${bench}/sites" "${baked_path}"

if [ -L "${assets_path}" ]; then
  ln -sfn "${baked_path}" "${assets_path}"
elif [ -d "${assets_path}" ]; then
  echo "qota-entrypoint: ${assets_path} is a real directory, so baked assets stay at ${baked_path}." >&2
  echo "qota-entrypoint: a nested sites/assets mount hides image assets. Remove that mount and recreate the container. This process does not delete the directory." >&2
elif [ -e "${assets_path}" ]; then
  echo "qota-entrypoint: ${assets_path} exists and is not a directory or symlink." >&2
  exit 1
else
  ln -s "${baked_path}" "${assets_path}"
fi

exec "$@"
