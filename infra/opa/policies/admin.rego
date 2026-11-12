# API action authorization (design D9).
#
#   POST /v1/data/opencg/admin/decision
#   {"input": {
#     "principal": {"id": "...", "roles": [...], "tenant": "...", "auth_method": "oidc"},
#     "action":    "entity.tombstone",
#     "resource":  "<entity id, run id, ...>"
#   }}
#
# `result`:
#
#   {"allow": false, "reason": "insufficient_role",
#    "package": "opencg.admin", "revision": "<meta.revision>"}
#
# Reasons, checked in this order:
#   unknown_action     the action is not in data/opencg.json `actions` (default deny)
#   no_role            the principal holds none of the roles the policy knows
#   allowed            the principal holds a role listed for the action
#   insufficient_role  otherwise
package opencg.admin

import data.opencg.common

decision := {
	"allow": reason == "allowed",
	"reason": reason,
	"package": "opencg.admin",
	"revision": common.revision,
}

# null when the input (or its action) is missing, so the lookup below is a
# plain miss (an undefined reference inside `not` would fail the clause instead).
default requested_action := null

requested_action := input.action

reason := "unknown_action" if {
	not data.actions[requested_action]
} else := "no_role" if {
	not common.has_known_role
} else := "allowed" if {
	some role in data.actions[requested_action]
	role in common.principal_roles
} else := "insufficient_role"
