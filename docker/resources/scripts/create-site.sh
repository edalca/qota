#!/bin/bash
set -euo pipefail
cd /home/frappe/frappe-bench

: "${SITE_NAME:?SITE_NAME is required}"
if [[ ! "$SITE_NAME" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then
  echo "SITE_NAME must be a site directory name." >&2
  exit 1
fi

site_dir="sites/$SITE_NAME"
pending="sites/.create-site-$SITE_NAME.pending"
exec 9>"sites/.create-site-$SITE_NAME.lock"
flock 9

if [[ -f "$site_dir/site_config.json" && ! -e "$pending" ]]; then
  echo "Site $SITE_NAME already exists. Skipping creation."
  exit 0
fi
if [[ -e "$site_dir" || -L "$site_dir" ]]; then
  echo "Site directory $site_dir exists and provisioning is incomplete." >&2
  exit 1
fi

: "${DB_HOST:?DB_HOST is required to create a site}"
: "${DB_ROOT_PASSWORD:?DB_ROOT_PASSWORD is required to create a site}"
: "${ADMIN_PASSWORD:?ADMIN_PASSWORD is required to create a site}"
DB_PORT="${DB_PORT:-3306}"
if [[ ! "$DB_PORT" =~ ^[0-9]{1,5}$ ]] || ((10#$DB_PORT < 1 || 10#$DB_PORT > 65535)); then
  echo "DB_PORT must be a port between 1 and 65535." >&2
  exit 1
fi

read -r -a apps <<< "${INSTALL_APPS:-qota}"
app_args=()
for app in "${apps[@]}"; do
  if ! grep -Fxq -- "$app" sites/apps.txt; then
    echo "App $app is unavailable in this image." >&2
    exit 1
  fi
  app_args+=("--install-app=$app")
done

echo "Waiting for MariaDB at $DB_HOST:$DB_PORT."
for attempt in {1..60}; do
  if timeout 2 bash -c 'exec 3<>"/dev/tcp/$1/$2"' _ "$DB_HOST" "$DB_PORT" 2>/dev/null; then
    break
  fi
  if [[ "$attempt" = 60 ]]; then
    echo "MariaDB is unavailable." >&2
    exit 1
  fi
  sleep 2
done

touch "$pending"
echo "Creating site $SITE_NAME."
# Invoke the same Frappe CLI that Bench uses without logging password arguments to bench.log.
(
  cd sites
  ../env/bin/python -m frappe.utils.bench_helper frappe new-site "$SITE_NAME" \
    --db-host "$DB_HOST" \
    --db-port "$DB_PORT" \
    --db-root-username "${DB_ROOT_USERNAME:-root}" \
    --db-root-password "$DB_ROOT_PASSWORD" \
    --admin-password "$ADMIN_PASSWORD" \
    --mariadb-user-host-login-scope "${MARIADB_USER_HOST_LOGIN_SCOPE:-%}" \
    --set-default \
    "${app_args[@]}" </dev/null
)
bench --site "$SITE_NAME" enable-scheduler
rm -- "$pending"
echo "Site $SITE_NAME created."
