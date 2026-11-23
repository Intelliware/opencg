package system.authz_test

import data.system.authz

req(method, path) if {
	authz.allow with input as {"method": method, "path": path}
}

test_decision_queries_allowed if {
	req("POST", ["v1", "data", "opencg", "entitlement", "decisions"])
	req("POST", ["v1", "data", "opencg", "admin", "decision"])
}

test_health_allowed if {
	req("GET", ["health"])
}

test_data_writes_refused if {
	not req("PUT", ["v1", "data", "actions"])
	not req("PATCH", ["v1", "data"])
	not req("PUT", ["v1", "data", "opencg", "admin"])
	not req("DELETE", ["v1", "data", "classifications"])
}

test_policy_uploads_and_other_reads_refused if {
	not req("PUT", ["v1", "policies", "x"])
	not req("GET", ["v1", "data", "opencg"])
	not req("GET", ["v1", "data"])
	not req("POST", ["v1", "data", "system", "authz"])
	not req("POST", ["v1", "data", "meta"])
}
