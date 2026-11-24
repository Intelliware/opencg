#!/usr/bin/env bash
# Refuse to publish Grafana beyond loopback with its default password
# (add-observability-stack, "Overlay ports stay on loopback by default").
# Prometheus and Tempo are always loopback-only; see the observability overlay.
set -euo pipefail

env_file="${ENV_FILE:-.env}"

# Value of KEY: the process environment wins, then the last assignment in .env.
value() {
	local key="$1"
	if [ -n "${!key:-}" ]; then
		printf '%s' "${!key}"
		return
	fi
	[ -f "$env_file" ] || return 0
	sed -n "s/^[[:space:]]*${key}=//p" "$env_file" | tail -n 1 | sed -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'$/\1/"
}

bind="$(value OPENCG__GRAFANA__BIND_ADDRESS)"
case "${bind:-127.0.0.1}" in
127.0.0.1 | ::1 | localhost) exit 0 ;;
esac

password="$(value OPENCG__GRAFANA__ADMIN_PASSWORD)"
if [ -z "$password" ] || [ "$password" = "admin" ]; then
	echo "OPENCG__GRAFANA__BIND_ADDRESS=$bind publishes Grafana beyond loopback, but" >&2
	echo "OPENCG__GRAFANA__ADMIN_PASSWORD is unset or 'admin'. Set a real password in .env" >&2
	echo "(see docs/OPERATIONS.md, Observability)." >&2
	exit 1
fi
