#!/bin/bash
# Move the assets produced by bench build outside the sites tree.
# Run this during image build, including in a derived image, after bench build.
# Do not run it against a mounted sites volume.
set -euo pipefail

bench="${BENCH_PATH:-/home/frappe/frappe-bench}"
baked="${bench}/assets"
link="${bench}/sites/assets"

mkdir -p "${bench}/sites" "${baked}"

if [ -L "${link}" ]; then
  current="$(readlink "${link}")"
  if [ "${current}" != "${baked}" ]; then
    rm -f "${link}"
    ln -s "${baked}" "${link}"
  fi
elif [ -d "${link}" ]; then
  cp -a "${link}/." "${baked}/"
  rm -rf "${link}"
  ln -s "${baked}" "${link}"
elif [ -e "${link}" ]; then
  echo "qota-bake-assets: ${link} is not a directory or symlink" >&2
  exit 1
else
  ln -s "${baked}" "${link}"
fi
