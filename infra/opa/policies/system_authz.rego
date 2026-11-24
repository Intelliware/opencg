# Who may call OPA's own REST API (OPA runs with --authorization=basic).
#
# Without this, OPA's API accepts writes: one `PUT /v1/data/...` could rewrite
# the roles in data/opencg.json and silently widen access, while decisions still
# report the committed policy revision. openCG services only ever POST decision
# queries under /v1/data/opencg/, and the healthcheck and readiness probes only
# GET /health; everything else (any PUT/PATCH/DELETE, policy uploads, reads of
# raw data) is refused with 401.
package system.authz

default allow := false

allow if {
	input.method == "POST"
	input.path[0] == "v1"
	input.path[1] == "data"
	input.path[2] == "opencg"
}

allow if {
	input.method == "GET"
	input.path == ["health"]
}
