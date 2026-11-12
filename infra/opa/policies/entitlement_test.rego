package opencg.entitlement_test

import data.opencg.entitlement

principal(roles) := {"id": "tester", "roles": roles, "tenant": "default", "auth_method": "oidc"}

candidate(id, classification) := {
	"entity_id": id,
	"classification": classification,
	"source": "git",
	"source_uri": "https://example.test/repo",
}

# One candidate through the whole policy; returns {"allow", "reason"}.
decide_one(roles, classification) := d if {
	result := entitlement.decisions with input as {
		"principal": principal(roles),
		"request": {"tool": "retrieve_for_context", "correlation_id": "c-1"},
		"candidates": [candidate("e1", classification)],
	}
	d := result.decisions.e1
}

test_public_and_internal_allowed_to_reader if {
	decide_one(["reader"], "public") == {"allow": true, "reason": "allowed"}
	decide_one(["reader"], "internal") == {"allow": true, "reason": "allowed"}
}

test_public_and_internal_allowed_to_admin if {
	decide_one(["admin"], "public") == {"allow": true, "reason": "allowed"}
	decide_one(["admin"], "internal") == {"allow": true, "reason": "allowed"}
}

test_confidential_legal_denied_without_legal if {
	decide_one(["reader"], "confidential:legal") == {"allow": false, "reason": "classification_restricted"}
	decide_one(["admin", "reader"], "confidential:legal") == {"allow": false, "reason": "classification_restricted"}
}

test_confidential_legal_allowed_with_legal if {
	decide_one(["reader", "legal"], "confidential:legal") == {"allow": true, "reason": "allowed"}
}

test_legal_only_principal_gets_legal_content_but_not_internal if {
	decide_one(["legal"], "confidential:legal") == {"allow": true, "reason": "allowed"}
	decide_one(["legal"], "internal") == {"allow": false, "reason": "classification_restricted"}
}

test_unknown_classification_denied_whatever_the_roles if {
	decide_one(["admin", "reader", "legal"], "secret") == {"allow": false, "reason": "unknown_classification"}
	decide_one([], "secret") == {"allow": false, "reason": "unknown_classification"}
}

test_undeclared_confidential_domain_is_unknown if {
	# `hr` is not in confidential_domains, so holding a role `hr` does not help.
	decide_one(["reader", "hr"], "confidential:hr") == {"allow": false, "reason": "unknown_classification"}
	decide_one(["reader", "legal"], "confidential:") == {"allow": false, "reason": "unknown_classification"}
	decide_one(["reader", "legal"], "confidential:legal:x") == {"allow": false, "reason": "unknown_classification"}
}

test_classification_is_case_sensitive if {
	decide_one(["reader"], "Internal") == {"allow": false, "reason": "unknown_classification"}
}

test_missing_classification_is_unknown if {
	result := entitlement.decisions with input as {
		"principal": principal(["reader"]),
		"request": {"tool": "retrieve_for_context", "correlation_id": "c-1"},
		"candidates": [{"entity_id": "e1", "source": "git", "source_uri": "x"}],
	}
	result.decisions.e1 == {"allow": false, "reason": "unknown_classification"}
}

test_empty_roles_get_no_role if {
	decide_one([], "internal") == {"allow": false, "reason": "no_role"}
	decide_one([], "confidential:legal") == {"allow": false, "reason": "no_role"}
}

test_unrecognised_roles_get_no_role if {
	decide_one(["viewer", "hr"], "public") == {"allow": false, "reason": "no_role"}
}

test_missing_roles_get_no_role if {
	result := entitlement.decisions with input as {
		"principal": {"id": "tester"},
		"candidates": [candidate("e1", "internal")],
	}
	result.decisions.e1 == {"allow": false, "reason": "no_role"}
}

test_batch_decides_each_candidate_and_echoes_package_and_revision if {
	result := entitlement.decisions with input as {
		"principal": principal(["reader"]),
		"request": {"tool": "retrieve_for_context", "correlation_id": "c-1"},
		"candidates": [
			candidate("a", "internal"),
			candidate("b", "confidential:legal"),
			candidate("c", "secret"),
			candidate("d", "public"),
		],
	}
	result == {
		"decisions": {
			"a": {"allow": true, "reason": "allowed"},
			"b": {"allow": false, "reason": "classification_restricted"},
			"c": {"allow": false, "reason": "unknown_classification"},
			"d": {"allow": true, "reason": "allowed"},
		},
		"package": "opencg.entitlement",
		"revision": data.meta.revision,
	}
}

test_no_candidates_gives_empty_decisions if {
	result := entitlement.decisions with input as {"principal": principal(["reader"]), "candidates": []}
	result.decisions == {}
	result.package == "opencg.entitlement"
}

test_mapping_comes_from_data if {
	# An operator grants `internal` to a new role by editing data only.
	decide_one(["auditor"], "internal") == {"allow": true, "reason": "allowed"} with data.classifications as {
		"public": ["reader", "admin"],
		"internal": ["reader", "admin", "auditor"],
	}
}
