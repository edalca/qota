# syntax=docker/dockerfile:1

# Qota runtime: Debian bookworm, official Frappe v16, and Qota.

ARG PYTHON_VERSION=3.14.3
ARG DEBIAN_VERSION=bookworm

FROM python:${PYTHON_VERSION}-slim-${DEBIAN_VERSION} AS base

ARG NODE_VERSION=24.13.0
ARG NVM_VERSION=v0.40.4
ARG YARN_VERSION=1.22.22
ARG BENCH_VERSION=5.29.1
ARG UV_VERSION=0.9.30
ARG WKHTMLTOPDF_VERSION=0.12.6.1-3

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NVM_DIR=/home/frappe/.nvm \
    PATH=/home/frappe/.nvm/versions/node/v${NODE_VERSION}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    LANG=C.UTF-8 \
    BASH_ENV=/home/frappe/.bashrc

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        file \
        fontconfig \
        fonts-liberation \
        gettext-base \
        git \
        gnupg \
        jq \
        libcairo2 \
        libffi8 \
        libfontconfig1 \
        libgl1 \
        libglib2.0-0 \
        libharfbuzz0b \
        libjpeg62-turbo \
        liblcms2-2 \
        libmariadb3 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libpangoft2-1.0-0 \
        libpq5 \
        libtiff6 \
        libwebp7 \
        libxext6 \
        libxrender1 \
        mariadb-client \
        media-types \
        nginx \
        passwd \
        pkg-config \
        postgresql-client \
        redis-tools \
        shared-mime-info \
        xfonts-75dpi \
        xfonts-base \
        zlib1g \
    && arch="$(dpkg --print-architecture)" \
    && case "${arch}" in \
         amd64|arm64) ;; \
         *) echo "unsupported architecture ${arch}" >&2; exit 1 ;; \
       esac \
    && curl -fsSL -o /tmp/wkhtmltox.deb \
         "https://github.com/wkhtmltopdf/packaging/releases/download/${WKHTMLTOPDF_VERSION}/wkhtmltox_${WKHTMLTOPDF_VERSION}.bookworm_${arch}.deb" \
    && apt-get install -y --no-install-recommends /tmp/wkhtmltox.deb \
    && rm -f /tmp/wkhtmltox.deb \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 frappe \
    && useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash frappe \
    && rm -f /etc/nginx/sites-enabled/default \
    && sed -i '/^user /d' /etc/nginx/nginx.conf \
    && sed -i 's|pid /run/nginx.pid;|pid /tmp/nginx.pid;|' /etc/nginx/nginx.conf \
    && rm -f /var/log/nginx/access.log /var/log/nginx/error.log \
    && ln -sf /dev/stdout /var/log/nginx/access.log \
    && ln -sf /dev/stderr /var/log/nginx/error.log \
    && mkdir -p /etc/nginx/snippets /etc/nginx/conf.d /var/lib/nginx /var/cache/nginx \
    && chown -R frappe:frappe /var/lib/nginx /var/log/nginx /var/cache/nginx /etc/nginx/conf.d \
    && pip3 install --no-cache-dir \
         "frappe-bench==${BENCH_VERSION}" \
         "uv==${UV_VERSION}"

USER frappe
RUN curl -fsSL "https://raw.githubusercontent.com/nvm-sh/nvm/${NVM_VERSION}/install.sh" | bash \
    && . "${NVM_DIR}/nvm.sh" \
    && nvm install "${NODE_VERSION}" \
    && nvm alias default "${NODE_VERSION}" \
    && npm install -g "yarn@${YARN_VERSION}" \
    && node --version \
    && yarn --version

USER root
RUN ln -sfn "/home/frappe/.nvm/versions/node/v${NODE_VERSION}/bin/node" /usr/local/bin/node \
    && ln -sfn "/home/frappe/.nvm/versions/node/v${NODE_VERSION}/bin/npm" /usr/local/bin/npm \
    && ln -sfn "/home/frappe/.nvm/versions/node/v${NODE_VERSION}/bin/npx" /usr/local/bin/npx \
    && ln -sfn "/home/frappe/.nvm/versions/node/v${NODE_VERSION}/bin/yarn" /usr/local/bin/yarn \
    && ln -sfn "/home/frappe/.nvm/versions/node/v${NODE_VERSION}/bin/corepack" /usr/local/bin/corepack

FROM base AS builder

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        default-libmysqlclient-dev \
        gcc \
        libcairo2-dev \
        libbz2-dev \
        libffi-dev \
        libgif-dev \
        libharfbuzz-dev \
        libjpeg-dev \
        liblcms2-dev \
        libldap2-dev \
        libmariadb-dev \
        libpango1.0-dev \
        libpq-dev \
        librsvg2-dev \
        libsasl2-dev \
        libssl-dev \
        libtiff5-dev \
        libwebp-dev \
        make \
        pkg-config \
        rlwrap \
        tk8.6-dev \
        wget \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

ARG FRAPPE_PATH=https://github.com/frappe/frappe
ARG FRAPPE_REF=version-16

ENV FRAPPE_DOCKER_BUILD=1 \
    UV_LINK_MODE=copy

USER frappe
WORKDIR /home/frappe

RUN bench init \
    --frappe-path "${FRAPPE_PATH}" \
    --frappe-branch "${FRAPPE_REF}" \
    --skip-assets \
    --no-procfile \
    --no-backups \
    --skip-redis-config-generation \
    /home/frappe/frappe-bench

ARG QOTA_PATH=https://github.com/edalca/qota.git
ARG QOTA_BRANCH=version-16
ARG QOTA_VERSION=

WORKDIR /home/frappe/frappe-bench

RUN bench get-app qota "${QOTA_PATH}" \
    --branch "${QOTA_VERSION:+v}${QOTA_VERSION:-${QOTA_BRANCH}}" \
    --skip-assets \
    && bench build \
    && find apps -mindepth 1 -path "*/.git" -exec rm -rf {} + \
    && mv /home/frappe/frappe-bench/sites/assets /home/frappe/frappe-bench/assets

FROM base AS runtime

ARG QOTA_VERSION=
ARG QOTA_REVISION=
ARG FRAPPE_PATH=https://github.com/frappe/frappe
ARG FRAPPE_REF=version-16
ARG FRAPPE_REF_KIND=branch

LABEL org.opencontainers.image.title="Qota" \
      org.opencontainers.image.description="Community water board management and billing on official Frappe v16" \
      org.opencontainers.image.source="https://github.com/edalca/qota" \
      org.opencontainers.image.vendor="edalca" \
      org.opencontainers.image.version="${QOTA_VERSION}" \
      org.opencontainers.image.revision="${QOTA_REVISION}" \
      org.opencontainers.image.authors="Edwin Alonso <edwinalonso162@hotmail.com>" \
      com.edalca.frappe.path="${FRAPPE_PATH}" \
      com.edalca.frappe.ref="${FRAPPE_REF}" \
      com.edalca.frappe.ref-kind="${FRAPPE_REF_KIND}"

COPY --from=builder --chown=frappe:frappe /home/frappe/frappe-bench /home/frappe/frappe-bench
COPY docker/resources/nginx/frappe.conf.template /templates/nginx/frappe.conf.template
COPY docker/resources/nginx/security_headers.conf /etc/nginx/snippets/security_headers.conf
COPY --chmod=755 docker/resources/nginx/nginx-entrypoint.sh /usr/local/bin/
COPY --chmod=755 docker/resources/scripts/*.sh /usr/local/bin/

USER frappe
WORKDIR /home/frappe/frappe-bench


EXPOSE 8000 8080 9000

ENTRYPOINT ["/usr/local/bin/main-entrypoint.sh"]
CMD ["/usr/local/bin/backend.sh"]
