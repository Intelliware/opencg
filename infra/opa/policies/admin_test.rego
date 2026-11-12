package opencg.admin_test

import data.opencg.admin

read_actions := ["retrieve", "search.vector", "audit.read", "entity.read", "graph.read", "ingestion.read"]

write_actions := ["entity.tombstone", "graph.write", "vocab.write", "ingestion.run"]

decide(roles, action) := d if {
	d := admin.decision with input as {
		"principal": {"id": "tester", "roles": roles, "tenant": "default", "auth_method": "oidc"},
		"action": action,
		"resource": "r-1",
	}
}

test_reader_gets_reads if {
	every action in read_actions {
		decide(["reader"], action) == {
			"allow": true,
			"reason": "allowed",
			"package": "opencg.admin",
			"revision": data.meta.revision,
		}
	}
}

test_reader_denied_writes if {
	every action in write_actions {
		d := decide(["reader"], action)
		d.allow == false
		d.reason == "insufficient_role"
	}
}

test_reader_denied_tombstone if {
	decide(["reader"], "entity.tombstone") == {
		"allow": false,
		"reason": "insufficient_role",
		"package": "opencg.admin",
		"revision": data.meta.revision,
	}
}

test_admin_gets_everything if {
	every action in array.concat(read_actions, write_actions) {
		decide(["admin"], action).allow == true
	}
}

test_every_configured_action_is_tested if {
	configured := {a | some a, _ in data.actions}
	configured == {a | some a in array.concat(read_actions, write_actions)}
}

test_unknown_action_denied if {
	decide(["admin"], "entity.purge") == {
		"allow": false,
		"reason": "unknown_action",
		"package": "opencg.admin",
		"revision": data.meta.revision,
	}
	decide([], "entity.purge").reason == "unknown_action"
}

test_missing_action_denied if {
	d := admin.decision with input as {"principal": {"id": "x", "roles": ["admin"]}}
	d.allow == false
	d.reason == "unknown_action"
}

test_empty_roles_get_no_role if {
	decide([], "retrieve") == {
		"allow": false,
		"reason": "no_role",
		"package": "opencg.admin",
		"revision": data.meta.revision,
	}
}

test_unrecognised_roles_get_no_role if {
	decide(["viewer"], "entity.read").reason == "no_role"
}

test_legal_only_principal_is_known_but_cannot_act if {
	decide(["legal"], "retrieve") == {
		"allow": false,
		"reason": "insufficient_role",
		"package": "opencg.admin",
		"revision": data.meta.revision,
	}
}

test_no_input_denied_as_unknown_action if {
	d := admin.decision with input as {}
	d == {"allow": false, "reason": "unknown_action", "package": "opencg.admin", "revision": data.meta.revision}
}
