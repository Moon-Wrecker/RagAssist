# syntax=docker/dockerfile:1
#
# Web image: the Vite single-page app (frontend/) served by nginx, same origin as the API (ADR 0014).
# Build from the repository root (the compose `web` service does):  docker build -f infra/docker/web.Dockerfile .
# The build context is trimmed by web.Dockerfile.dockerignore (next to this file), not by the root .dockerignore.
#
# No host, port, credential or API address is baked in: nginx renders its configuration from environment
# variables when the container starts (see infra/nginx/ and the required WEB_* variables in .env.example).

# Both images are pinned. Bump deliberately; for a fully reproducible build pin by digest as well, e.g.
#   --build-arg NGINX_IMAGE=nginx/nginx-unprivileged:1.30.6-alpine@sha256:<digest>
ARG NODE_IMAGE=node:22-alpine
ARG NGINX_IMAGE=nginx/nginx-unprivileged:1.30.6-alpine

# --- Build stage: the same checks the CI `frontend` job builds with (type-check, then vite build) ---
FROM ${NODE_IMAGE} AS build
WORKDIR /app

# Dependencies first so the layer is cached until the lockfile changes. `npm ci` installs exactly what the lock says.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# `npm run build` is `tsc --noEmit && vite build`; a type error fails the image build.
RUN npm run build

# --- Runtime stage: only the built assets and the nginx templates ---
FROM ${NGINX_IMAGE}

# Official nginx image mechanism: every /etc/nginx/templates/*.template is run through envsubst at start and written
# to /etc/nginx/conf.d without the suffix. nginx-unprivileged runs as a non-root user and keeps its pid and temp
# files in /tmp, so the container needs no extra capability and no writable root filesystem path besides /tmp
# and /etc/nginx/conf.d.
COPY infra/nginx/templates/ /etc/nginx/templates/
# Sourced by the entrypoint before the templates are rendered: refuses to start with a missing variable.
COPY infra/nginx/15-web-env.envsh /docker-entrypoint.d/15-web-env.envsh
COPY --from=build /app/dist/ /usr/share/nginx/html/

# The listen port comes from WEB_PORT at run time, so there is no EXPOSE here; compose publishes it.
