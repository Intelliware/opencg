#!/bin/bash
# Entrypoint for the bundled Keycloak (compose service `keycloak`, profile `idp`).
#
# Chooses what to import and how to start from OPENCG__ENVIRONMENT (unset means
# production, like every other openCG service):
#
#   dev, test            start-dev --import-realm; imports the realm AND the dev
#                        users (alice, bob, carol); smoke service accounts enabled
#   staging, production  start --import-realm (production mode, plain HTTP behind
#                        the operator's TLS proxy, X-Forwarded-* trusted); realm
#                        only: no users, smoke service accounts disabled
#
# Keycloak's directory import reads <realm>-realm.json plus <realm>-users-N.json,
# so the committed files are copied into the import directory under those names,
# and the users file only in dev/test. Placeholders like ${OPENCG__...} in both
# files are resolved by Keycloak from this container's environment at import.
#
# Import happens once, when the realm does not exist yet in Keycloak's database
# (strategy IGNORE_EXISTING). Changing OPENCG__ENVIRONMENT later does not add or
# remove users: recreate the `keycloak` database for that (docs/OPERATIONS.md).
set -euo pipefail

src=/opt/opencg/keycloak
import_dir=/opt/keycloak/data/import
env="${OPENCG__ENVIRONMENT:-production}"

die() { echo "keycloak-entrypoint: $*" >&2; exit 1; }

require() {
	local name
	for name in "$@"; do
		[ -n "${!name:-}" ] || die "$name must be set (see .env.example, bundled Keycloak section)"
	done
}

case "$env" in
dev | test | staging | production) ;;
*) die "OPENCG__ENVIRONMENT must be dev, test, staging or production (got '$env')" ;;
esac

require KC_DB_PASSWORD KC_BOOTSTRAP_ADMIN_PASSWORD OPENCG__ADMIN_UI__OIDC__CLIENT_SECRET OPENCG__ADMIN_UI__PUBLIC_URL

mkdir -p "$import_dir"
rm -f "$import_dir"/*.json
cp "$src/realm-opencg.json" "$import_dir/opencg-realm.json"

case "$env" in
dev | test)
	require OPENCG__SMOKE__CLIENT_SECRET OPENCG__SMOKE_READER__CLIENT_SECRET OPENCG__SMOKE_LEGAL__CLIENT_SECRET \
		OPENCG__IDP__ALICE_PASSWORD OPENCG__IDP__BOB_PASSWORD OPENCG__IDP__CAROL_PASSWORD
	cp "$src/realm-opencg-dev-users.json" "$import_dir/opencg-users-0.json"
	export OPENCG_KEYCLOAK_TEST_CLIENTS_ENABLED=true
	echo "keycloak-entrypoint: OPENCG__ENVIRONMENT=$env: dev mode, importing the opencg realm with dev users"
	mode=(start-dev)
	;;
staging | production)
	# The smoke clients exist but are disabled; give them unguessable secrets
	# so an unset placeholder never becomes a known one.
	export OPENCG_KEYCLOAK_TEST_CLIENTS_ENABLED=false
	export OPENCG__SMOKE__CLIENT_SECRET="$(cat /proc/sys/kernel/random/uuid)"
	export OPENCG__SMOKE_READER__CLIENT_SECRET="$(cat /proc/sys/kernel/random/uuid)"
	export OPENCG__SMOKE_LEGAL__CLIENT_SECRET="$(cat /proc/sys/kernel/random/uuid)"
	export KC_PROXY_HEADERS="${KC_PROXY_HEADERS:-xforwarded}"
	echo "keycloak-entrypoint: OPENCG__ENVIRONMENT=$env: production mode, importing the opencg realm without users"
	mode=(start)
	;;
esac

exec /opt/keycloak/bin/kc.sh "${mode[@]}" --import-realm "$@"
