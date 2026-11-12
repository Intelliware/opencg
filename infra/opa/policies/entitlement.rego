# Per-candidate retrieval entitlement (design D8).
#
# The pipeline sends ONE request per retrieval:
#
#   POST /v1/data/opencg/entitlement/decisions
#   {"input": {
#     "principal":  {"id": "...", "roles": [...], "tenant": "...", "auth_method": "oidc"},
#     "request":    {"tool": "retrieve_for_context", "correlation_id": "..."},
#     "candidates": [{"entity_id": "...", "classification": "internal",
#                     "source": "git", "source_uri": "..."}]
#   }}
#
# and reads `result`:
#
#   {"decisions": {"<entity_id>": {"allow": true, "reason": "allowed"}},
#    "package": "opencg.entitlement", "revision": "<meta.revision>"}
#
# Reasons, checked in this order:
#   unknown_classification  the classification is not in data/opencg.json
#                           (`classifications`, or `confidential:<domain>` with
#                           <domain> in `confidential_domains`); denied whatever
#                           the principal's roles, so a typo never widens access
#   no_role                 the principal holds none of the roles the policy knows
#   allowed                 the principal holds a role the classification needs
#   classification_restricted  otherwise
package opencg.entitlement

import data.opencg.common

confidential_prefix := "confidential:"

decisions := {
	"decisions": {c.entity_id: decide(c) | some c in input.candidates},
	"package": "opencg.entitlement",
	"revision": common.revision,
}

decide(candidate) := {"allow": r == "allowed", "reason": r} if {
	r := reason(candidate)
}

reason(candidate) := "unknown_classification" if {
	not known_classification(candidate)
} else := "no_role" if {
	not common.has_known_role
} else := "allowed" if {
	permitted(candidate)
} else := "classification_restricted"

known_classification(candidate) if {
	data.classifications[candidate.classification]
}

known_classification(candidate) if {
	domain := confidential_domain(candidate.classification)
	domain in data.confidential_domains
}

# `public`, `internal`, ...: any of the roles listed for the classification.
permitted(candidate) if {
	some role in data.classifications[candidate.classification]
	role in common.principal_roles
}

# `confidential:<domain>`: the role named <domain>.
permitted(candidate) if {
	domain := confidential_domain(candidate.classification)
	domain in data.confidential_domains
	domain in common.principal_roles
}

confidential_domain(classification) := domain if {
	is_string(classification)
	startswith(classification, confidential_prefix)
	domain := substring(classification, count(confidential_prefix), -1)
	domain != ""
}
