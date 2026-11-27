## 1. Policy and personas

- [ ] 1.1 Add `wealth`, `payments` and `retail` to `confidential_domains` in `infra/opa/data/opencg.json`, plus one policy test per domain. Run `make opa-revision && make opa-test`
- [ ] 1.2 `demo/personas.json`: the five personas and their roles (design D4)
- [ ] 1.3 Persona creation in `demo/scripts/seed.sh` through `kcadm.sh` in the Keycloak container: idempotent roles and users, passwords from `OPENCG__DEMO__PASSWORD`, refused unless `OPENCG__ENVIRONMENT=dev`. Add the `dev-only-*` placeholder to `.env.example`
- [ ] 1.4 Optional per-persona dev API keys (`DEMO_API_KEYS=1`): print each raw key once, append only hashes to the keys file

## 2. Content

- [ ] 2.1 `demo/packs/group/internal/`: AML/ATF programme summary, complaint-handling standard, data classification standard
- [ ] 2.2 Wealth pack (design D2), with README, disclaimer and owner
- [ ] 2.3 Payments pack (design D2), with README, disclaimer and owner
- [ ] 2.4 Retail pack (design D2), with README, disclaimer and owner
- [ ] 2.5 `demo/questions.json`: at least three split-answer questions per pack (question, internal document, confidential document, persona)
- [ ] 2.6 Review all content for real institution or person names, and for figures that read as real guidance

## 3. Tooling

- [ ] 3.1 `infra/compose/docker-compose.demo.yml`: mount `demo/packs` read-only into ingestion, and set `OPENCG__INGESTION__GIT__LOCAL_ROOTS=/tmp`
- [ ] 3.2 `demo/scripts/seed.sh`: copy, `git init` and commit, then ingest each `(pack, classification)` with the CLI; ingest `group` once; warn and continue when no chat API key is set
- [ ] 3.3 `demo/scripts/reset.sh`: tombstone entities by source prefix, and the concepts whose only sources are those entities
- [ ] 3.4 Makefile: `demo-up` (oidc mode, `idp` profile, demo overlay), `demo-seed PACK=…`, `demo-reset PACK=…`, `demo-smoke`

## 4. Demo smoke check

- [ ] 4.1 `demo/scripts/smoke.sh`:
  - seed with the chat stub;
  - assert the entity count per prefix;
  - assert split answers for each persona and question from `demo/questions.json`;
  - reset
- [ ] 4.2 Show it failing: temporarily grant `demo-reader` the `payments` role, and the check must name the question and persona
- [ ] 4.3 Add `make demo-smoke` to the nightly schedule of the CI `stack` job

## 5. Guide and docs

- [ ] 5.1 `docs/DEMO.md` (design D8): prerequisites, bring-up, seeding, Claude Code, Claude Desktop (`mcp-remote`; connector with a tunnel as an option) and Cursor, connection checks, persona switching, per-pack scripts, trace/audit/cost walkthrough in Grafana, reset, known limitations (graph entitlement), troubleshooting
- [ ] 5.2 README "Try the demo" section, OPERATIONS link, CHANGELOG entry
- [ ] 5.3 Follow `docs/DEMO.md` end to end on a fresh clone: Claude Code over OAuth as `demo-reader` and as `demo-payments-ops`, and Cursor with an API key. Record the results here

## 6. Verify and ship

- [ ] 6.1 `openspec validate add-showcase-seed-packs --strict`
- [ ] 6.2 `make ci-static`, `make smoke`, `make demo-smoke`
- [ ] 6.3 Set the `ROADMAP.md` item to `in-progress` when implementation starts. Commit, push and open the PR
- [ ] 6.4 After merge: `openspec archive add-showcase-seed-packs`, and delete the roadmap item in the same PR
