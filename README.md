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

The root Dockerfile builds Frappe v16 and Qota without declaring any `VOLUME`
instructions. Persistence for `/home/frappe/frappe-bench/sites` and
`/home/frappe/frappe-bench/logs` is managed by the operator in Docker Compose
(using any site-appropriate volume names) rather than baked into the image. Use
the same image revision for all services in a deployment. Replace any inline
initialization commands with the following Compose commands, running each setup
job once per deployment:

```yaml
services:
  configurator:
    command: ["/usr/local/bin/configure.sh"]
    volumes:
      - sites:/home/frappe/frappe-bench/sites
      - logs:/home/frappe/frappe-bench/logs
  create-site:
    command: ["/usr/local/bin/create-site.sh"]
    environment:
      INSTALL_APPS: "${INSTALL_APPS:-qota}"
    volumes:
      - sites:/home/frappe/frappe-bench/sites
      - logs:/home/frappe/frappe-bench/logs
    depends_on:
      configurator:
        condition: service_completed_successfully
  backend:
    volumes:
      - sites:/home/frappe/frappe-bench/sites
      - logs:/home/frappe/frappe-bench/logs
    depends_on:
      create-site:
        condition: service_completed_successfully
```

The image entrypoint `/usr/local/bin/main-entrypoint.sh` links
`/home/frappe/frappe-bench/sites/assets` to `/home/frappe/frappe-bench/assets`
before executing the service command. Keep any general `entrypoint` override
cleared in Compose so every service uses this entrypoint and supplies only its
`command` (for example `/usr/local/bin/configure.sh`,
`/usr/local/bin/create-site.sh`, `/usr/local/bin/nginx-entrypoint.sh`, or the
default `/usr/local/bin/backend.sh`). Mount persistent volumes on
`/home/frappe/frappe-bench/sites` and `/home/frappe/frappe-bench/logs` (the
exact volume names are up to your Compose stack, such as `sites`/`logs` or
`qota-sites`/`qota-logs`), and do not mount a separate volume on `sites/assets`.

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
Database upgrades for existing sites are controlled and never automatic at
startup: run `bench --site <site> migrate` explicitly as a separate operational
step.

Compiled bundles and manifests (`assets.json`, `assets-rtl.json`, and app
asset links) are built during `docker build` and stored inside the image at
`/home/frappe/frappe-bench/assets`, outside the persistent `sites` volume.
`ASSETS_PATH` has been removed: Nginx serves `/assets/` directly from
`/home/frappe/frappe-bench/assets/` via `alias`, while Frappe reads
`sites/assets` through the symlink created at startup by `main-entrypoint.sh`.
`configure.sh` verifies that `sites/assets` links to
`/home/frappe/frappe-bench/assets`, validates `assets.json`, `assets-rtl.json`,
and all referenced asset files without copying manifests into the `sites`
volume, and invalidates the Redis key `assets_json`.

When upgrading from an older deployment:

- If a separate volume or bind mount is attached to
  `/home/frappe/frappe-bench/sites/assets`, `main-entrypoint.sh` detects the
  mount conflict, leaves existing data untouched, and stops with an error.
  Remove the `sites/assets` mount from the service configuration and recreate
  the containers.
- If `sites/assets` is a legacy real directory inside the `sites` volume (and
  not a mountpoint), `main-entrypoint.sh` verifies that it is either empty or
  contains only recognized Frappe asset entries (`assets.json`,
  `assets-rtl.json`, `css`, `js`, `locale`, and app links/directories) before
  replacing it with the symlink to `/home/frappe/frappe-bench/assets`.
  Directories containing any unrecognized files or folders, or non-directory
  entries, are left untouched with an error.

Derived images (such as `qota-private`) can extend this image with Messaging
and `qota_preset`. Because the base image declares no `VOLUME` instructions,
changes across separate `RUN` instructions persist normally during `docker
build`, and derived images inherit `ENTRYPOINT` and `CMD` unless they
explicitly override them. Install the additional apps, build all assets, and
replace `/home/frappe/frappe-bench/assets` with the newly compiled
`sites/assets` (leaving no second asset tree under `sites/`):

```dockerfile
FROM edalca/qota:latest

RUN bench get-app messaging <MESSAGING_REPO> --branch <BRANCH> --skip-assets
RUN bench get-app qota_preset <QOTA_PRESET_REPO> --branch <BRANCH> --skip-assets
RUN bench build \
    && rm -rf /home/frappe/frappe-bench/assets \
    && mv /home/frappe/frappe-bench/sites/assets /home/frappe/frappe-bench/assets
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
