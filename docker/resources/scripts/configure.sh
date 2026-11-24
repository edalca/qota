#!/bin/bash
set -euo pipefail
cd /home/frappe/frappe-bench

: "${DB_HOST:?DB_HOST is required}"
: "${REDIS_CACHE:?REDIS_CACHE is required}"
: "${REDIS_QUEUE:?REDIS_QUEUE is required}"

port() {
  if [[ ! "$2" =~ ^[0-9]{1,5}$ ]] || ((10#$2 < 1 || 10#$2 > 65535)); then
    echo "$1 must be a port between 1 and 65535." >&2
    return 1
  fi
  printf '%s\n' "$((10#$2))"
}

redis_url() {
  local url="$2" host_port
  if [[ "$url" != *://* ]]; then
    url="redis://$url"
  fi
  host_port="${url#*://}"
  host_port="${host_port%%[/?#]*}"
  host_port="${host_port##*@}"
  if [[ ! "$url" =~ ^rediss?:// || ! "$host_port" =~ ^(\[[^]]+\]|[^:[:space:]]+)(:([0-9]{1,5}))?$ ]]; then
    echo "$1 must be a valid Redis endpoint." >&2
    return 1
  fi
  port "$1" "${BASH_REMATCH[3]:-6379}" >/dev/null || return 1
  printf '%s\n' "$url"
}

temporary=""
trap '
  if [[ -n "$temporary" ]]; then rm -f -- "$temporary"; fi
' EXIT

write_file() {
  local path="$1" mode="$2"
  temporary="$(mktemp "${path%/*}/.${path##*/}.XXXXXX")"
  cat > "$temporary"
  if [[ ! -L "$path" ]] && cmp -s -- "$temporary" "$path"; then
    rm -- "$temporary"
  else
    chmod "$mode" "$temporary"
    sync -d "$temporary"
    mv -fT -- "$temporary" "$path"
  fi
  temporary=""
}

validate_asset_manifest() {
  jq -es '
    select(length == 1) | .[] | select(type == "object" and length > 0)
    | all(.[]; type == "string" and startswith("/assets/")
      and (startswith("/assets//") | not)
      and (split("/") | index("..") | not)
      and (test("[\\r\\n]") | not))
  ' "$1" >/dev/null
}

decode_asset_reference() {
  local LC_ALL=C path="${1#/assets/}" decoded="" octet
  case "$path" in *\?* | *\#*) return 1 ;; esac

  # Resolve the URL path once, as it is decoded for a request.
  while [[ "$path" == *%* ]]; do
    decoded+="${path%%\%*}"
    path="${path#*%}"
    if [[ ! "$path" =~ ^[0-9a-fA-F]{2} || "${path:0:2}" == 00 ]]; then
      return 1
    fi
    printf -v octet '%b' "\\x${path:0:2}"
    decoded+="$octet"
    path="${path:2}"
  done
  decoded+="$path"
  case "/$decoded/" in
    *//* | */../* | */./* | *\\* | *[[:cntrl:]]*) return 1 ;;
  esac
  printf '%s' "$decoded"
}

resolve_asset_file() {
  local root="$1" relative_path="$2" file
  if ! IFS= read -r -d '' file < <(realpath -ze -- "${root%/}/$relative_path" 2>/dev/null); then
    printf 'Asset file is missing or unreachable: %q\n' "$relative_path" >&2
    return 1
  fi
  if [[ "$file" != "${root%/}/"* && "$file" != "/home/frappe/frappe-bench/apps/"*"/public/"* ]]; then
    printf 'Asset path escapes bench asset trees: %q\n' "$relative_path" >&2
    return 1
  fi
  if [[ ! -f "$file" || ! -r "$file" ]]; then
    printf 'Expected a readable asset file: %q\n' "$relative_path" >&2
    return 1
  fi
}

validate_baked_assets() {
  local baked_root="$1" name manifest reference relative_path
  shift
  if [[ ! -d "$baked_root" || ! -r "$baked_root" || ! -x "$baked_root" ]]; then
    echo "Compiled assets directory $baked_root must exist and be readable." >&2
    return 1
  fi
  if [[ ! -L sites/assets ]] || [[ "$(realpath -e -- sites/assets 2>/dev/null || true)" != "$baked_root" ]]; then
    echo "sites/assets must link to $baked_root." >&2
    return 1
  fi

  for name in "$@"; do
    manifest="${baked_root}/${name}"
    if [[ ! -f "$manifest" || ! -r "$manifest" ]]; then
      printf 'Missing asset manifest: %s\n' "$manifest" >&2
      return 1
    fi
    # jq can replace malformed UTF-8 bytes, so also verify the raw input round trip.
    if ! jq -Rrsj '.' "$manifest" | cmp -s -- "$manifest" - ||
      ! validate_asset_manifest "$manifest"; then
      printf 'Invalid asset manifest: %s\n' "$name" >&2
      return 1
    fi
    while IFS= read -r reference; do
      if ! relative_path="$(decode_asset_reference "$reference")"; then
        printf 'Unsafe asset path in %s: %q\n' "$name" "$reference" >&2
        return 1
      fi
      resolve_asset_file "$baked_root" "$relative_path"
    done < <(
      jq -r '.[] | if (explode | any(. < 32 or . == 127))
        then error("Control character in asset path") else . end' \
        "$manifest"
    )
  done
}

db_port="$(port DB_PORT "${DB_PORT:-3306}")"
socketio_port="$(port SOCKETIO_PORT "${SOCKETIO_PORT:-9000}")"
redis_cache="$(redis_url REDIS_CACHE "$REDIS_CACHE")"
redis_queue="$(redis_url REDIS_QUEUE "$REDIS_QUEUE")"
redis_socketio="$(redis_url REDIS_SOCKETIO "${REDIS_SOCKETIO:-$REDIS_QUEUE}")"

exec 9>sites/.qota-configure.lock
flock 9

config_path=sites/common_site_config.json
config='{}'
if [[ -e "$config_path" ]]; then
  config="$(< "$config_path")"
fi
config="$(jq -esS \
  --arg db_host "$DB_HOST" --argjson db_port "$db_port" \
  --arg redis_cache "$redis_cache" --arg redis_queue "$redis_queue" \
  --arg redis_socketio "$redis_socketio" --argjson socketio_port "$socketio_port" \
  'select(length == 1) | .[] | objects + {
    $db_host, $db_port, $redis_cache, $redis_queue, $redis_socketio, $socketio_port
  }' <<< "$config")"

if [[ ! -d apps/frappe/frappe || ! -d apps/qota/qota ]]; then
  echo "Frappe and Qota must be present in the image." >&2
  exit 1
fi
apps=()
for path in apps/*; do
  app="${path##*/}"
  if [[ -d "$path/$app" ]]; then
    apps+=("$app")
  fi
done

manifests=(assets.json assets-rtl.json)
validate_baked_assets /home/frappe/frappe-bench/assets "${manifests[@]}"

write_file sites/apps.txt 644 <<< "$(printf '%s\n' "${apps[@]}")"
write_file "$config_path" 600 <<< "$config"

# Use explicit CLI options for IPv6 and database numbers supplied in the URI query.
cache_url="${redis_cache%%\?*}"
cache_args=()
if [[ "$cache_url" =~ ^(rediss?://([^/]*@)?)\[([^]]+)\](.*)$ ]]; then
  cache_args+=(-h "${BASH_REMATCH[3]}")
  cache_url="${BASH_REMATCH[1]}localhost${BASH_REMATCH[4]}"
fi
if [[ "$redis_cache" = *\?* && "${redis_cache#*\?}" =~ (^|\&)db=([0-9]+)(\&|$) ]]; then
  cache_args+=(-n "${BASH_REMATCH[2]}")
fi
timeout 5 redis-cli -e --no-auth-warning -u "$cache_url" "${cache_args[@]}" DEL assets_json >/dev/null

echo "Bench configuration and image asset manifests are ready."
