## Why

openCG's headline features are hard to show to a financial-services audience:
- policy-based access control, where two people asking the same question get different answers;
- a knowledge graph built from the organisation's own documents;
- per-request traces with token cost.

The only seeded data is the smoke fixture: a handful of generic AI-tooling notes, all at one classification, with no personas. A demo today means hand-writing documents, ingesting each classification separately, creating users and roles in Keycloak by hand, and working out how to connect each AI tool.

Electric Mind's focus segments are wealth, payments and retail banking. Each needs a repeatable demo that runs on a laptop from a fresh clone, uses no client data, and makes the access-control difference obvious.

## What Changes

- **Three synthetic content packs** under `demo/packs/{wealth,payments,retail}/`, set at a single fictional financial group, plus a shared `demo/packs/group/internal/` folder (AML programme, complaint handling, data classification) that every seed run ingests. Each pack has about 8–12 Markdown documents (product sheets, procedures, runbooks, policies), split into `public/`, `internal/` and `confidential/` folders. The `confidential` folder is ingested as `confidential:<pack>`.
  - Documents name each other, shared products and real public regulations, so the knowledge graph has relationships to find.
  - Several questions are written so the `internal` document refers to a `confidential` one ("thresholds are set by the fraud team"). A persona without the domain role gets the referral; one with the role gets the detail.
- **Demo personas:**
  - **Roles:** `confidential_domains` in `infra/opa/data/opencg.json` gains `wealth`, `payments` and `retail`. These roles do nothing for anyone who doesn't hold them.
  - **Users:** `make demo-seed` creates the users idempotently in the bundled Keycloak through its admin CLI, only when `OPENCG__ENVIRONMENT` is `dev`. They are `demo-advisor` (wealth), `demo-payments-ops` (payments), `demo-branch` (retail), `demo-compliance` (all three) and `demo-reader` (no domain role).
  - The committed realm and its dev users are unchanged.
  - Per-persona dev API keys are available for tools that can't sign in with OAuth.
- **Make targets:**
  - `make demo-up` starts the stack in `oidc` mode with the bundled Keycloak and a `docker-compose.demo.yml` overlay, which mounts the packs read-only into ingestion.
  - `make demo-seed PACK=wealth|payments|retail|all` ingests each classification folder as its own run and creates the personas. Re-running it is safe.
  - `make demo-reset PACK=…` tombstones the pack's entities and the concepts extracted only from them.
- **`docs/DEMO.md`:**
  - prerequisites;
  - bring-up and seeding;
  - connecting Claude Code, Claude Desktop and Cursor over MCP, with OAuth sign-in as a persona or a per-persona API key as fallback;
  - a per-pack script: the questions to ask, what each persona should see, which graph view to open, and where to find the trace and cost in Grafana;
  - reset and troubleshooting.
- **Demo smoke check:** `make demo-smoke`, run in the nightly `stack` job. For each pack it seeds, then asserts that every classification ingested and that the persona differences hold for each scripted question. It uses the deterministic chat stub, so CI needs no Ollama Cloud key.

## Capabilities

### New Capabilities

- `showcase-packs`: the synthetic demo content, its classifications, the demo personas, the seed/reset tooling, the demo guide and the demo smoke check.

### Modified Capabilities

<!-- none. The extra confidential domains are policy data; no existing requirement lists the allowed domains. The committed Keycloak realm and its dev users are unchanged. -->

## Impact

- **New files:**
  - `demo/packs/**` (synthetic Markdown, about 30–36 documents);
  - `demo/personas.json`;
  - `demo/scripts/{seed,reset,smoke}.sh`;
  - `infra/compose/docker-compose.demo.yml`;
  - `docs/DEMO.md`.
- **Changed:**
  - `infra/opa/data/opencg.json` (three domains; revision regenerated) and its policy tests;
  - `Makefile` (`demo-up`, `demo-seed`, `demo-reset`, `demo-smoke`);
  - `.github/workflows/ci.yml` (nightly demo smoke);
  - README (a "Try the demo" section), OPERATIONS (a link), CHANGELOG.
- **Runtime services:** no code changes. Seeding uses the existing ingestion CLI and its local-root allow-list (`OPENCG__INGESTION__GIT__LOCAL_ROOTS`), as the smoke test does.
- **Cost:** the knowledge-graph part of the demo uses Ollama Cloud extraction, which needs the user's own API key. Seeding all three packs once costs well under US$1 at the published `gemma4:31b` rates, and the trace view shows the exact figure. Without a key, ingestion and retrieval still work, but the graph only has code-derived and smoke-stub concepts.
- **Data:** fully synthetic. A fictional group, fictional people, no client names, and a disclaimer in every pack's README that the content is illustrative and not legal or regulatory guidance.
- **Depends on:**
  - `add-identity-and-opa` (shipped; OIDC, OPA, classifications);
  - its open manual check 13.3 (Claude Code over OAuth), which the demo guide relies on.
  - The demo graph also shows concepts to `demo-reader` that come from confidential documents until `add-graph-entitlement` ships. The guide says so, and the script avoids the graph view for that persona.
