# Helpers shared by opencg.entitlement and opencg.admin.
#
# Every role, classification and action lives in data/opencg.json, so an
# operator changes who may see what without editing Rego. After editing either
# file run `make opa-revision`, then `make opa-test`.
package opencg.common

# The policy revision every decision echoes: SHA-256 of the policy and data
# files (see infra/opa/revision.py). `make opa-test` fails when it is stale.
revision := data.meta.revision

# The caller's roles as a set. A missing or malformed roles list is empty.
principal_roles := {r | some r in input.principal.roles; is_string(r)}

# Every role the policy grants something to. A principal holding none of them
# is authenticated but entitled to nothing (reason `no_role`).
known_roles contains role if {
	some roles in data.classifications
	some role in roles
}

known_roles contains role if {
	some roles in data.actions
	some role in roles
}

known_roles contains domain if {
	some domain in data.confidential_domains
}

has_known_role if {
	some role in principal_roles
	role in known_roles
}
