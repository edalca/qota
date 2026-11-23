### Qota

Community water board management and billing system

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch version-16
bench install-app qota
```

### Docker deployments

The root Dockerfile builds Frappe v16 and Qota. Use the same image revision for
all services in a deployment. In Coolify, keep the existing image reference,
environment, and named mounts. Replace the inline initialization commands with
the following Compose commands. Run each job once per deployment.

```yaml
services:
  configurator:
    command: ["/usr/local/bin/configure.sh"]
  create-site:
    command: ["/usr/local/bin/create-site.sh"]
    environment:
      INSTALL_APPS: "${INSTALL_APPS:-qota}"
    depends_on:
      configurator:
        condition: service_completed_successfully
  backend:
    depends_on:
      create-site:
        condition: service_completed_successfully
```

Keep the same `create-site` dependency on frontend, scheduler, workers, and
WebSocket, alongside their existing dependencies. Clear any general entrypoint
override so Compose runs the service commands directly. Use
`/usr/local/bin/backend.sh` for an explicit backend command and
`/usr/local/bin/nginx-entrypoint.sh` for the frontend. Keep the mounts
`qota-sites:/home/frappe/frappe-bench/sites` and
`qota-logs:/home/frappe/frappe-bench/logs` as they are.

`configure.sh` reads `DB_HOST`, `REDIS_CACHE` and `REDIS_QUEUE` from the
environment. `DB_PORT` defaults to 3306, `SOCKETIO_PORT` defaults to 9000, and
`REDIS_SOCKETIO` defaults to `REDIS_QUEUE`. Redis endpoints may be written as
`host:port[/db]` or as Redis URLs.

`create-site.sh` uses `SITE_NAME` to identify the site. An existing site skips
creation. For a new site, the job requires `DB_HOST`, `DB_ROOT_PASSWORD`, and
`ADMIN_PASSWORD`. `DB_PORT` defaults to 3306 and `DB_ROOT_USERNAME` to `root`.
`MARIADB_USER_HOST_LOGIN_SCOPE` defaults to `%` so the other containers can
connect with the site database user.

Set `INSTALL_APPS` to a space-separated list in installation order. It defaults
to `qota`. A derived image can use `INSTALL_APPS="qota messaging qota_preset"`.
The job checks that the apps are available and passes them to `bench new-site`.
It selects the new site and enables its scheduler. If creation is interrupted
and leaves a site directory, the job reports the incomplete provisioning.
Upgrades of existing sites use `bench --site <site> migrate` separately.

Bench writes bundles and manifests under `/home/frappe/frappe-bench/sites/assets`.
Nginx serves `/assets/` from that directory by default. To serve bundles from
another directory, set the same absolute `ASSETS_PATH` on the configurator
and frontend, and make the same source files available to both. For example,
add this bind mount alongside the existing mounts.

```yaml
services:
  configurator:
    environment:
      ASSETS_PATH: /mnt/frappe-assets
    volumes:
      - /srv/qota-assets:/mnt/frappe-assets:ro
  frontend:
    environment:
      ASSETS_PATH: /mnt/frappe-assets
    volumes:
      - /srv/qota-assets:/mnt/frappe-assets:ro
```

Frappe reads `assets.json` and `assets-rtl.json` from `sites/assets` in the
sites volume. With the override, the configurator validates both source
manifests and checks that their referenced files resolve inside that directory.
It copies only changed manifests into `sites/assets`. Populate the alternate
directory with both manifests and their bundles before running the jobs.
Without the override, the configurator validates the manifests already in the
volume. It invalidates the Redis key `assets_json` after successful configuration.

When upgrading from 16.10.1, check `sites/assets` in the existing sites volume
before starting the configurator. If it still links to the retired image
directory, replace just that link with a real `sites/assets` directory.
Populate or refresh that directory with assets from the matching image when
using the default path. With an alternate source, prepare the destination
directory for the configurator and supply the bundles at the alternate mount.

The private Image Builder can continue to extend this image with Messaging
and qota_preset. Add both apps to the derived image with Bench before compiling
their bundles. Bench writes the build output to `sites/assets`.

```dockerfile
RUN bench build --app frappe,qota,messaging,qota_preset
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/qota
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
