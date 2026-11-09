#!/bin/bash
# Creates the restricted application role (no superuser, no BYPASSRLS) so row-level security binds it.
# Runs once from /docker-entrypoint-initdb.d on a fresh volume. Name and password come from the environment
# (APP_DB_USER / APP_DB_PASSWORD, set by compose from .env); nothing is hardcoded here.
set -euo pipefail

: "${APP_DB_USER:?APP_DB_USER is required}"
: "${APP_DB_PASSWORD:?APP_DB_PASSWORD is required}"

# psql variables are quoted by :'name' (literal) and format(%I/%L), so the values can contain any character.
psql -v ON_ERROR_STOP=1 \
     -v app_user="$APP_DB_USER" -v <redacted>="$APP_DB_PASSWORD" \
     --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'EOSQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOBYPASSRLS', :'app_user', :'<redacted>')
 WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'app_user') \gexec
SELECT format('GRANT ALL PRIVILEGES ON DATABASE %I TO %I', current_database(), :'app_user') \gexec
SELECT format('GRANT ALL ON SCHEMA public TO %I', :'app_user') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO %I', :'app_user') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO %I', :'app_user') \gexec
EOSQL
