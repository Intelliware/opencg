## Context

- **Ingestion** takes a git repository and stamps one classification on every entity in the run (`--classification`). Remote URLs must be `https`, `ssh` or `git`. Local paths are accepted only under `OPENCG__INGESTION__GIT__LOCAL_ROOTS`, which the smoke overlay sets to `/tmp`. The smoke runner copies its committed fixture into `/tmp/opencg-smoke-<run>`, runs `git init` and a commit there, and ingests it with the CLI inside the ingestion container (`tests/smoke/lib.sh`).
- **Entitlement:**
  - `public` and `internal` need `reader` or `admin`;
  - `confidential:<domain>` needs the `<domain>` role, and `<domain>` must be listed in `confidential_domains` in `infra/opa/data/opencg.json`. Today that list is `["legal"]`.
- **The bundled Keycloak** imports its realm (roles `admin`, `reader`, `legal`) and the dev users (`alice`, `bob`, `carol`) once, when the realm doesn't exist yet. The `identity-access` spec fixes that realm's contents.
- **API keys** (`make api-key NAME=… ROLES=…`) carry a principal and roles, and are accepted only in `dev`.
- **Knowledge-graph text extraction** calls the chat provider (Ollama Cloud `gemma4:31b` by default). Extraction is best-effort, so ingest never fails because of it.

## Goals / Non-Goals

**Goals:**
- From a fresh clone, a presenter can reach a working three-pack demo with three commands and one guide.
- Asking the same question as two personas visibly gives different answers, and the reason (a classification) can be traced in the audit and access logs.
- The knowledge graph shows recognisable banking concepts and relationships.
- The demo can't silently rot: CI exercises it.
- No client data, real people or real institutions.

**Non-Goals:**
- Structured data or text-to-SQL. Those are roadmap items `add-structured-data-routing` and `add-ossie-import`.
- Production use of the personas. Seeding refuses to run outside `dev`.
- Hosting a public demo instance.
- Exhaustive or legally accurate regulatory content.

## Decisions

### D1. One fictional group, three lines of business

All packs are set at **Juniper Bay Financial Group** (fictional), headquartered in Canada:
- **Juniper Bay Wealth** for the wealth pack;
- **Juniper Bay Payments** for payments;
- **Juniper Bay Bank** for retail.

A shared group means cross-pack relationships exist: the group AML policy is referenced by all three, and so is the complaint-handling standard. Canada fits Electric Mind's market. Public regulations and standards are named by their real titles (for example PCMLTFA and FINTRAC reporting, OSFI guidelines, ISO 20022, Payments Canada's Lynx and RTR, CIRO suitability rules) and described only at a high level. Every pack README says that the institution, people and figures are fictional, and that nothing in the pack is legal or regulatory guidance.

*Alternatives:* a separate fictional institution per pack loses the cross-pack graph. A US setting is less relevant to the primary audience; the packs are plain Markdown, so a fork can relocalise them.

### D2. Pack layout and content

```
demo/packs/<pack>/
  README.md                 # what the pack shows, disclaimer, questions
  public/*.md               # product sheets, fee schedules, published service standards
  internal/*.md             # procedures, runbooks, onboarding checklists
  confidential/*.md         # thresholds, scoring cut-offs, exception registers
```

- Each pack has about 8–12 documents of 300–900 words, so ingest is quick and retrieval is meaningful.
- Documents name each other by title, so the extractor finds `references`, `depends_on`, `supersedes` and `defined_in` relationships.
- Each pack has at least **three scripted questions** with a split answer: the `internal` document defers to a named `confidential` one, and the `confidential` one holds the specifics.

**Wealth (`confidential:wealth`):**
- public: managed portfolio family, fee schedule, and client onboarding guide;
- internal: KYC refresh procedure, suitability review, model-portfolio rebalancing runbook, complaints handling;
- confidential: the suitability exception register policy, high-net-worth segmentation thresholds, and the advisor compensation grid.

**Payments (`confidential:payments`):**
- public: wire and EFT fees and cut-off times, and the real-time payments service guide;
- internal: wire repair and returns runbook, ISO 20022 migration notes, payment incident runbook, sanctions alert triage;
- confidential: fraud detection rules and thresholds, sanctions screening tuning, and high-value payment approval limits.

**Retail (`confidential:retail`):**
- public: chequing and savings disclosures, overdraft protection terms, and the dispute and chargeback guide;
- internal: account-opening procedure, branch cash-handling standard, dispute investigation procedure, hardship programme;
- confidential: the credit decisioning policy with score cut-offs, the collections strategy, and pricing exception authorities.

**Group (`internal`, shared):** the AML/ATF programme summary, complaint-handling standard and data classification standard. These live in `demo/packs/group/internal/` and are ingested with every `PACK=…` (once).

### D3. Seeding reuses the smoke-fixture mechanism

`docker-compose.demo.yml` mounts `demo/packs` read-only into ingestion at `/opt/opencg/demo-packs` and sets `OPENCG__INGESTION__GIT__LOCAL_ROOTS=/tmp`. For each `(pack, classification)`, `demo/scripts/seed.sh`:

1. copies the folder to `/tmp/opencg-demo-<pack>-<classification>` and runs `git init` and a commit there;
2. runs the ingestion CLI with `--classification public|internal|confidential:<pack>`.

The source URI prefix becomes `git://opencg-demo-<pack>-<classification>/`, which `demo-reset` and the smoke check use to find the pack's entities.

Content hashing makes re-runs cheap. A re-run after a reset restores tombstoned entities, as any re-ingest does.

*Alternatives:*
- Serving packs from a public GitHub repo would need network access and a second repository.
- Adding a "directory" connector would be a feature in itself, and belongs on the roadmap if wanted.

### D4. Personas are created at seed time, not in the committed realm

`seed.sh` runs Keycloak's admin CLI (`kcadm.sh`) inside the Keycloak container, authenticating as the bootstrap admin from the environment. It creates realm roles `wealth`, `payments` and `retail`, and the users in `demo/personas.json`:

| User | Roles | Shows |
|---|---|---|
| `demo-advisor` | reader, wealth | wealth specifics, nothing confidential from payments or retail |
| `demo-payments-ops` | reader, payments | payments specifics |
| `demo-branch` | reader, retail | retail specifics |
| `demo-compliance` | reader, wealth, payments, retail | everything |
| `demo-reader` | reader | only public and internal; the referral, never the specifics |

- Each step is idempotent: existing objects are updated, not duplicated.
- Passwords come from `OPENCG__DEMO__PASSWORD`. `.env.example` sets a `dev-only-*` placeholder, so the existing dev-only guard refuses it outside `dev`/`test`.
- `seed.sh` refuses to run unless `OPENCG__ENVIRONMENT=dev`.

`seed.sh` also writes one dev API key per persona when asked (`DEMO_API_KEYS=1`), for tools without OAuth. It prints each raw key once and appends only the hash to the keys file.

*Alternative:* adding the roles and users to `realm-opencg.json`. That changes the `identity-access` realm requirement, and only takes effect on a fresh Keycloak database, whereas `kcadm` works on a running stack.

### D5. Three more confidential domains in the policy data

`confidential_domains` becomes `["legal", "wealth", "payments", "retail"]`. These are inert without the matching role, and no spec lists the allowed domains. A policy test is added per domain, and `make opa-revision` regenerates the revision.

*Alternative:* a demo-only OPA data file. OPA merges data documents by path, so a second file can't extend the same list without restructuring the policy data.

### D6. Extraction: real model for demos, stub for CI

- `make demo-seed` uses the configured chat provider (Ollama Cloud with the user's key), so the graph has real concepts. Without a key it warns once and continues, and the guide's graph steps are marked optional.
- `make demo-smoke` seeds with the deterministic chat stub (as `make smoke` does), so CI needs no key and is reproducible.

### D7. Demo smoke check

`demo/scripts/smoke.sh`, run by `make demo-smoke` and the nightly `stack` job (not every PR, to keep PR CI fast):
1. seeds all packs with the stub;
2. asserts that the expected number of entities exists per `(pack, classification)` prefix;
3. for every scripted question, gets client-credentials or API-key tokens for `demo-reader` and the domain persona, calls `/retrieve`, and asserts that the persona sees a fragment from the confidential document while `demo-reader` doesn't;
4. resets.

The scripted questions live in `demo/questions.json`, so `docs/DEMO.md` and the check use the same list.

### D8. Connecting tools

`docs/DEMO.md` documents, for each tool:
- **Claude Code:** `claude mcp add --transport http opencg http://localhost:8181/mcp`, then sign in as a persona through the bundled Keycloak.
- **Claude Desktop:** the `mcp-remote` bridge to the same URL. A claude.ai custom connector needs a publicly reachable HTTPS URL, so it's documented as an option with a tunnel, not the default.
- **Cursor:** an `mcp.json` entry with the URL, and an API-key header as fallback.
- **Switching persona:** sign out in the Keycloak account page, or switch API keys.

Each tool section ends with a one-line check ("ask: *what are the wire cut-off times?*") that proves the connection before the demo starts.

## Risks / Trade-offs

- **OAuth with Claude Code is not yet verified by hand** (`add-identity-and-opa` 13.3). → The guide's API-key fallback covers every tool, and 13.3 is done before this change ships.
- **Graph leak until `add-graph-entitlement`:** `demo-reader` can see concepts extracted from confidential documents in `/graph`. → The demo script doesn't show the graph as `demo-reader`, and the guide states the limitation and links the roadmap item.
- **Realistic-looking thresholds could be mistaken for real guidance.** → The disclaimer in every README, deliberately round numbers, and a fictional institution.
- **Retrieval is probabilistic:** a scripted question might not surface the intended document. → The smoke check asserts on the stub-embedded stack. Questions are worded with each document's distinctive terms, and tuned until they pass reliably.
- **Content upkeep.** → It's plain Markdown with one owner per pack, listed in the pack README.

## Open Questions

- Are the group name **Juniper Bay Financial Group** and the Canadian setting acceptable, or should the owner pick another name or jurisdiction?
- Should the demo smoke check run on every PR instead of nightly? It adds about 2–3 minutes to `stack`.
