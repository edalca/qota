#!/bin/bash
# Link compiled image assets into the sites directory before running a service.
# Refuses destructive changes if an independent mount or unrecognized directory exists.
set -euo pipefail

umask 0002

BENCH_PATH="/home/frappe/frappe-bench"
SITES_DIR="${BENCH_PATH}/sites"
SITE_ASSETS_PATH="${SITES_DIR}/assets"
BAKED_PATH="${BENCH_PATH}/assets"

is_mountpoint_or_has_submount() {
  local target="$1"
  if command -v mountpoint >/dev/null 2>&1 && mountpoint -q "$target"; then
    return 0
  fi
  if [[ -r /proc/self/mountinfo ]]; then
    local mp
    while IFS=' ' read -r _ _ _ _ mp _; do
      mp="${mp//\\040/ }"
      mp="${mp//\\011/$'\t'}"
      mp="${mp//\\012/$'\n'}"
      mp="${mp//\\134/\\}"
      if [[ "$mp" == "$target" || "$mp" == "${target}/"* ]]; then
        return 0
      fi
    done < /proc/self/mountinfo
  fi
  return 1
}

is_recognized_legacy_assets_dir() {
  local dir="$1"
  local has_entries=0 has_marker=0 entry base

  if [[ ! -r "$dir" || ! -x "$dir" ]]; then
    return 1
  fi

  while IFS= read -r -d '' entry; do
    has_entries=1
    base="${entry##*/}"
    case "$base" in
      assets.json|assets-rtl.json)
        if [[ ! -f "$entry" || -L "$entry" ]]; then
          return 1
        fi
        has_marker=1
        ;;
      css|js|locale)
        if [[ ! -d "$entry" || -L "$entry" ]]; then
          return 1
        fi
        ;;
      frappe)
        if [[ ! -d "$entry" && ! -L "$entry" ]]; then
          return 1
        fi
        has_marker=1
        ;;
      qota|messaging|qota_preset)
        if [[ ! -d "$entry" && ! -L "$entry" ]]; then
          return 1
        fi
        ;;
      *)
        if [[ -d "${BENCH_PATH}/apps/${base}" && ( -d "$entry" || -L "$entry" ) ]]; then
          :
        else
          return 1
        fi
        ;;
    esac
  done < <(find "$dir" -mindepth 1 -maxdepth 1 -print0)

  if (( ! has_entries || has_marker )); then
    return 0
  fi
  return 1
}

if is_mountpoint_or_has_submount "$SITE_ASSETS_PATH" || is_mountpoint_or_has_submount "$BAKED_PATH"; then
  echo "main-entrypoint: an independent volume or sub-mount is active on ${SITE_ASSETS_PATH} or ${BAKED_PATH}, conflicting with compiled image assets." >&2
  echo "main-entrypoint: remove the sites/assets mount and recreate the container; existing data was left untouched." >&2
  exit 1
fi

if [[ ! -d "$BAKED_PATH" ]]; then
  echo "main-entrypoint: compiled image assets directory ${BAKED_PATH} is missing." >&2
  exit 1
fi

# Fast path when the link is already configured, including read-only sites mounts.
if [[ -L "$SITE_ASSETS_PATH" ]] && [[ "$(readlink -- "$SITE_ASSETS_PATH")" == "$BAKED_PATH" ]]; then
  exec "$@"
fi

mkdir -p "$SITES_DIR"
if [[ ! -w "$SITES_DIR" ]]; then
  echo "main-entrypoint: ${SITES_DIR} is not writable; cannot link ${SITE_ASSETS_PATH} -> ${BAKED_PATH}." >&2
  exit 1
fi

tmp_link=""
cleanup_link() {
  if [[ -n "$tmp_link" ]]; then
    rm -f -- "$tmp_link"
  fi
}
trap cleanup_link EXIT

exec 9>"${SITES_DIR}/.qota-assets-link.lock"
flock 9

if is_mountpoint_or_has_submount "$SITE_ASSETS_PATH" || is_mountpoint_or_has_submount "$BAKED_PATH"; then
  echo "main-entrypoint: an independent volume or sub-mount is active on ${SITE_ASSETS_PATH} or ${BAKED_PATH}, conflicting with compiled image assets." >&2
  echo "main-entrypoint: remove the sites/assets mount and recreate the container; existing data was left untouched." >&2
  exit 1
fi

if [[ -L "$SITE_ASSETS_PATH" ]]; then
  if [[ "$(readlink -- "$SITE_ASSETS_PATH")" != "$BAKED_PATH" ]]; then
    echo "Updating sites/assets symlink to ${BAKED_PATH}..."
    tmp_link="$(mktemp -u "${SITES_DIR}/.assets-link.XXXXXX")"
    ln -s "$BAKED_PATH" "$tmp_link"
    mv -Tf -- "$tmp_link" "$SITE_ASSETS_PATH"
    tmp_link=""
  fi
elif [[ -d "$SITE_ASSETS_PATH" ]]; then
  if ! is_recognized_legacy_assets_dir "$SITE_ASSETS_PATH"; then
    echo "main-entrypoint: ${SITE_ASSETS_PATH} is a non-empty directory that does not appear to be a legacy Frappe assets directory. Refusing to remove it automatically." >&2
    exit 1
  fi
  echo "Replacing legacy sites/assets directory with symlink to ${BAKED_PATH}..."
  rm -rf -- "$SITE_ASSETS_PATH"
  tmp_link="$(mktemp -u "${SITES_DIR}/.assets-link.XXXXXX")"
  ln -s "$BAKED_PATH" "$tmp_link"
  mv -Tf -- "$tmp_link" "$SITE_ASSETS_PATH"
  tmp_link=""
elif [[ -e "$SITE_ASSETS_PATH" ]]; then
  echo "main-entrypoint: ${SITE_ASSETS_PATH} exists and is not a directory or symlink. Refusing to remove it." >&2
  exit 1
else
  echo "Linking fresh assets to sites volume..."
  tmp_link="$(mktemp -u "${SITES_DIR}/.assets-link.XXXXXX")"
  ln -s "$BAKED_PATH" "$tmp_link"
  mv -Tf -- "$tmp_link" "$SITE_ASSETS_PATH"
  tmp_link=""
fi

exec 9>&-
trap - EXIT

exec "$@"
