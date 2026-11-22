#!/bin/bash
# Fetch one official Frappe revision and initialize the bench without assets.
# Asset compilation happens after Qota is installed.
set -euo pipefail

: "${FRAPPE_PATH:?FRAPPE_PATH is required}"
: "${FRAPPE_REF:?FRAPPE_REF is required}"
: "${FRAPPE_REF_KIND:?FRAPPE_REF_KIND is required}"

case "${FRAPPE_PATH}" in
  https://github.com/frappe/frappe | https://github.com/frappe/frappe.git) ;;
  *)
    echo "FRAPPE_PATH must be https://github.com/frappe/frappe" >&2
    exit 1
    ;;
esac

case "${FRAPPE_REF}" in
  "" | -* | *" "* | *".."*)
    echo "FRAPPE_REF is empty or unsafe: ${FRAPPE_REF}" >&2
    exit 1
    ;;
esac

case "${FRAPPE_REF_KIND}" in
  branch)
    refspec="refs/heads/${FRAPPE_REF}"
    ;;
  tag)
    refspec="refs/tags/${FRAPPE_REF}"
    ;;
  commit)
    refspec="${FRAPPE_REF}"
    ;;
  *)
    echo "FRAPPE_REF_KIND must be branch, tag, or commit" >&2
    exit 1
    ;;
esac

# The directory name must be "frappe". bench clones that basename into apps/.
src="/tmp/frappe"
rm -rf "${src}"
git init -q "${src}"
git -C "${src}" remote add origin "${FRAPPE_PATH}"
git -C "${src}" fetch --depth 1 origin "${refspec}"
git -C "${src}" checkout --detach FETCH_HEAD
git -C "${src}" checkout -B qota-build-pin

actual="$(git -C "${src}" rev-parse HEAD)"
if [ -n "${FRAPPE_REVISION:-}" ] && [ "${actual}" != "${FRAPPE_REVISION}" ]; then
  echo "Frappe revision ${actual} does not match FRAPPE_REVISION ${FRAPPE_REVISION}" >&2
  exit 1
fi
echo "Frappe ${FRAPPE_REF_KIND} ${FRAPPE_REF} resolved to ${actual}"

cd /home/frappe
bench init \
  --python python3 \
  --frappe-path "${src}" \
  --frappe-branch qota-build-pin \
  --skip-assets \
  --no-procfile \
  --no-backups \
  --skip-redis-config-generation \
  /home/frappe/frappe-bench

bench_path="/home/frappe/frappe-bench"
if [ -d "${bench_path}/apps/frappe-src" ] && [ ! -e "${bench_path}/apps/frappe/.git" ]; then
  rm -rf "${bench_path}/apps/frappe"
  mv "${bench_path}/apps/frappe-src" "${bench_path}/apps/frappe"
fi
git -C "${bench_path}/apps/frappe" remote set-url upstream "${FRAPPE_PATH}"
upstream="$(git -C "${bench_path}/apps/frappe" remote get-url upstream)"
case "${upstream}" in
  https://github.com/frappe/frappe | https://github.com/frappe/frappe.git) ;;
  *)
    echo "Frappe remote is not the official repository: ${upstream}" >&2
    exit 1
    ;;
esac
if git -C "${bench_path}/apps/frappe" remote -v | grep -q 'edalca/frappe'; then
  echo "Refusing a bench that still points at edalca/frappe" >&2
  exit 1
fi

installed="$(git -C "${bench_path}/apps/frappe" rev-parse HEAD)"
if [ "${installed}" != "${actual}" ]; then
  echo "Installed Frappe revision ${installed} does not match fetched revision ${actual}" >&2
  exit 1
fi

version="$(
  "${bench_path}/env/bin/python" -c 'import pathlib, re; text = pathlib.Path("/home/frappe/frappe-bench/apps/frappe/frappe/__init__.py").read_text(); print(re.search(r"__version__\s*=\s*[\"'"'"']([^\"'"'"']+)", text).group(1))'
)"
case "${version}" in
  16.*) ;;
  *)
    echo "Installed Frappe version ${version} is not version 16" >&2
    exit 1
    ;;
esac
echo "Installed official Frappe ${version} at ${installed}"

if [ ! -f "${bench_path}/apps/frappe/socketio.js" ]; then
  echo "socketio.js is missing from the Frappe checkout" >&2
  ls -la "${bench_path}/apps" >&2
  find "${bench_path}/apps/frappe" -maxdepth 2 -name 'socketio.js' -o -name 'package.json' >&2
  exit 1
fi
test ! -d "${bench_path}/apps/messaging"
test ! -d "${bench_path}/apps/qota_preset"
rm -rf "${src}"
