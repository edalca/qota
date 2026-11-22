#!/bin/bash
# Render the Frappe nginx site and run nginx in the foreground as the frappe user.
# This process does not create sites, install apps, migrate, or build assets.
set -euo pipefail

umask 0002

if [[ -z "${BACKEND:-}" ]]; then
  echo "BACKEND defaulting to 0.0.0.0:8000"
  export BACKEND=0.0.0.0:8000
fi
if [[ -z "${SOCKETIO:-}" ]]; then
  echo "SOCKETIO defaulting to 0.0.0.0:9000"
  export SOCKETIO=0.0.0.0:9000
fi
if [[ -z "${NGINX_LISTEN_PORT:-}" ]]; then
  echo "NGINX_LISTEN_PORT defaulting to 8080"
  export NGINX_LISTEN_PORT=8080
fi
# The previous Qota image trusted X-Forwarded-Proto. Keep that behavior unless
# the operator sets TRUST_UPSTREAM_FORWARDED_PROTO=off.
if [[ -z "${TRUST_UPSTREAM_FORWARDED_PROTO:-}" ]]; then
  export TRUST_UPSTREAM_FORWARDED_PROTO=on
fi
case "$TRUST_UPSTREAM_FORWARDED_PROTO" in
  on | off) ;;
  *)
    echo "TRUST_UPSTREAM_FORWARDED_PROTO must be on or off" >&2
    exit 1
    ;;
esac
if [[ -z "${UPSTREAM_REAL_IP_ADDRESS:-}" ]]; then
  echo "UPSTREAM_REAL_IP_ADDRESS defaulting to 127.0.0.1"
  export UPSTREAM_REAL_IP_ADDRESS=127.0.0.1
fi
if [[ -z "${UPSTREAM_REAL_IP_HEADER:-}" ]]; then
  echo "UPSTREAM_REAL_IP_HEADER defaulting to X-Forwarded-For"
  export UPSTREAM_REAL_IP_HEADER=X-Forwarded-For
fi
if [[ -z "${UPSTREAM_REAL_IP_RECURSIVE:-}" ]]; then
  echo "UPSTREAM_REAL_IP_RECURSIVE defaulting to off"
  export UPSTREAM_REAL_IP_RECURSIVE=off
fi
if [[ -z "${FRAPPE_SITE_NAME_HEADER:-}" ]]; then
  # shellcheck disable=SC2016
  echo 'FRAPPE_SITE_NAME_HEADER defaulting to $host'
  # shellcheck disable=SC2016
  export FRAPPE_SITE_NAME_HEADER='$host'
fi
if [[ -z "${PROXY_READ_TIMEOUT:-}" ]]; then
  echo "PROXY_READ_TIMEOUT defaulting to 120"
  export PROXY_READ_TIMEOUT=120
fi
if [[ -z "${CLIENT_MAX_BODY_SIZE:-}" ]]; then
  echo "CLIENT_MAX_BODY_SIZE defaulting to 50m"
  export CLIENT_MAX_BODY_SIZE=50m
fi

# shellcheck disable=SC2016
envsubst '${BACKEND}
  ${SOCKETIO}
  ${NGINX_LISTEN_PORT}
  ${TRUST_UPSTREAM_FORWARDED_PROTO}
  ${UPSTREAM_REAL_IP_ADDRESS}
  ${UPSTREAM_REAL_IP_HEADER}
  ${UPSTREAM_REAL_IP_RECURSIVE}
  ${FRAPPE_SITE_NAME_HEADER}
  ${PROXY_READ_TIMEOUT}
  ${CLIENT_MAX_BODY_SIZE}' \
  </templates/nginx/frappe.conf.template >/etc/nginx/conf.d/frappe.conf

exec nginx -g 'daemon off;'
