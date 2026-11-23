#!/bin/bash
# Database and role for the bundled Keycloak (compose service `keycloak`,
# profile `idp`). Keycloak keeps its realms, registered clients and sessions
# here, so they survive container restarts; `make down-v` removes them with
# the rest of the Postgres volume.
#
# The `keycloak` role owns only the `keycloak` database. It gets no grants on
# the openCG database or its `opencg` schema, so a Keycloak upgrade cannot touch
# openCG tables.
#
# Runs as the Postgres superuser: at first start of an empty volume (the image's
# docker-entrypoint-initdb.d), or on an existing volume with
#   make db-apply SQL=015_keycloak_db.sh
# Re-runnable: creates what is missing and resets the role's password to
# OPENCG__KEYCLOAK__DB_PASSWORD. Skipped (with a notice) when that variable is
# unset, which is the case in `none` auth mode with the default .env.
set -euo pipefail

if [ -z "${OPENCG__KEYCLOAK__DB_PASSWORD:-}" ]; then
	echo "015_keycloak_db: OPENCG__KEYCLOAK__DB_PASSWORD is unset; not creating the keycloak database." \
		"Set it and run 'make db-apply SQL=015_keycloak_db.sh' before using the bundled Keycloak."
	exit 0
fi

psql=(psql -v ON_ERROR_STOP=1 --no-psqlrc --username "$POSTGRES_USER" --dbname "${POSTGRES_DB:-postgres}")

# Password passed as a psql variable (:'kc_password' quotes it as a literal),
# so it is never interpolated into the SQL text by the shell.
"${psql[@]}" -v kc_password="$OPENCG__KEYCLOAK__DB_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE keycloak LOGIN PASSWORD %L', :'kc_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'keycloak') \gexec
SELECT format('ALTER ROLE keycloak LOGIN PASSWORD %L', :'kc_password') \gexec
SELECT 'CREATE DATABASE keycloak OWNER keycloak'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'keycloak') \gexec
REVOKE ALL ON DATABASE keycloak FROM PUBLIC;
GRANT CONNECT ON DATABASE keycloak TO keycloak;
SQL

echo "015_keycloak_db: keycloak role and database ready"
