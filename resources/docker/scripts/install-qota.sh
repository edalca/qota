#!/bin/bash
# Install the Qota checkout that Docker sent as the build context.
# Do not clone Qota again and do not install Messaging or qota_preset.
set -euo pipefail

bench_path="/home/frappe/frappe-bench"
src="/tmp/qota-src"
cd "${bench_path}"

rm -rf apps/qota
mkdir -p apps/qota
cp -a "${src}/." apps/qota/
rm -rf apps/qota/resources apps/qota/.github
rm -f apps/qota/Dockerfile apps/qota/.dockerignore

source_version="$(
  python3 -c 'import pathlib, re; text = pathlib.Path("/home/frappe/frappe-bench/apps/qota/qota/__init__.py").read_text(); print(re.search(r"__version__\s*=\s*[\"'"'"']([^\"'"'"']+)", text).group(1))'
)"
if [ -n "${QOTA_VERSION:-}" ] && [ "${source_version}" != "${QOTA_VERSION}" ]; then
  echo "Qota source version ${source_version} does not match QOTA_VERSION ${QOTA_VERSION}" >&2
  exit 1
fi

./env/bin/python -m pip install --upgrade -e apps/qota

if [ -f apps/qota/package.json ]; then
  yarn --cwd apps/qota install --check-files
fi

python3 - <<'PY'
from bench.bench import Bench

Bench("/home/frappe/frappe-bench").apps.sync(
    app_name="qota",
    app_dir="qota",
    branch=None,
    required=[],
)
PY

grep -qx frappe sites/apps.txt
grep -qx qota sites/apps.txt
test ! -d apps/messaging
test ! -d apps/qota_preset

# One production build covers Frappe and Qota, including the shared manifest.
bench build
rm -rf apps/qota/node_modules

/usr/local/bin/qota-bake-assets
test -L sites/assets
test "$(readlink sites/assets)" = "${bench_path}/assets"
test -f assets/assets.json
test -f assets/assets-rtl.json

python3 - <<'PY'
import json
import os
import pathlib
import re

bench = pathlib.Path("/home/frappe/frappe-bench")

def version(app):
    text = (bench / "apps" / app / app / "__init__.py").read_text()
    match = re.search(r"__version__\s*=\s*[\"']([^\"']+)", text)
    if not match:
        raise SystemExit(f"missing __version__ in {app}")
    return match.group(1)

manifest = json.dumps(json.loads((bench / "assets" / "assets.json").read_text()))
for name in ("frappe", "qota"):
    if name not in manifest:
        raise SystemExit(f"assets.json does not mention {name}")

frappe_revision = os.popen("git -C /home/frappe/frappe-bench/apps/frappe rev-parse HEAD").read().strip()
payload = {
    "frappe": {
        "path": os.environ["FRAPPE_PATH"],
        "ref": os.environ["FRAPPE_REF"],
        "ref_kind": os.environ["FRAPPE_REF_KIND"],
        "revision": frappe_revision,
        "version": version("frappe"),
    },
    "qota": {
        "version": version("qota"),
        "revision": os.environ.get("QOTA_REVISION") or None,
        "source": "build-context",
    },
}
if not str(payload["frappe"]["version"]).startswith("16."):
    raise SystemExit("Frappe version is not 16")
destination = bench / "config" / "image-source.json"
destination.write_text(json.dumps(payload, indent=2) + "\n")
print(destination.read_text())
PY

printf '%s\n' '{}' > sites/common_site_config.json
rm -rf "${src}"
