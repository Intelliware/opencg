# openCG demo: wealth, payments and retail banking

This guide runs openCG's showcase on a laptop. It uses three synthetic content packs set at a fictional group, Juniper Bay Financial Group, and covers three things:

1. **The same question, different answers.** Each person sees only what their role allows. A branch employee is pointed to a confidential policy; the credit team gets the figures.
2. **A knowledge graph built from the documents.** Products, procedures, policies and regulations are linked to each other.
3. **Every answer traced and costed.** Each request is audited, and its tokens and estimated cost are recorded.

> Juniper Bay Financial Group is fictional. Its people, figures and documents are illustrative and are not legal or regulatory guidance.

## 1. Prerequisites

- Docker with Compose v2, about 8 GB of free memory, `make`, `python3` and `curl`.
- A fresh clone with `cp .env.example .env`. The example's defaults are what the demo expects, including `OPENCG__ENVIRONMENT=dev`.
- **Optional:** an Ollama Cloud API key in `OPENCG__PROVIDERS__CHAT__API_KEY`. It powers knowledge-graph extraction. Without it, documents still ingest and every persona demo works, but the graph shows no extracted concepts. Seeding all three packs once costs well under US$1 at the published rates, and the admin UI shows the exact figure.
- **One AI tool:** Claude Code, Claude Desktop or Cursor.

## 2. Start and seed

```bash
make demo-up              # stack in signed-in (oidc) mode with the bundled Keycloak; first run builds images
make demo-seed            # personas + all packs; or PACK=wealth|payments|retail
```

`make demo-up OBS=1` adds Prometheus, Tempo and Grafana (about 700 MB more) for the trace walkthrough in step 5. Re-running `make demo-seed` is safe: personas are updated, and documents keep their IDs, so nothing is duplicated.

**What seeding creates:**

| Persona | Roles | Sees |
|---|---|---|
| `demo-reader` | reader | Public and internal documents only. Gets the referral, never the specifics |
| `demo-advisor` | reader, wealth | Wealth's confidential documents |
| `demo-payments-ops` | reader, payments | Payments' confidential documents |
| `demo-branch` | reader, retail | Retail's confidential documents |
| `demo-compliance` | reader, wealth, payments, retail | Everything |

Every persona's password is the value of `OPENCG__DEMO__PASSWORD` in `.env`. Each pack's documents are ingested by folder: `public`, `internal`, and `confidential` as `confidential:<pack>`. The shared group standards are ingested as `internal`.

## 3. Connect an AI tool

The MCP server is at `http://localhost:8181/mcp`. It's an OAuth-protected resource, so each tool signs in through the bundled Keycloak, and you choose the persona at the sign-in page.

**Claude Code**
```bash
claude mcp add --transport http opencg http://localhost:8181/mcp
```
Start `claude`, run `/mcp`, choose **opencg → Authenticate**, and sign in as a persona.

**Claude Desktop.** Add this to `claude_desktop_config.json`, restart, and sign in when the browser opens:
```json
{ "mcpServers": { "opencg": { "command": "npx", "args": ["mcp-remote", "http://localhost:8181/mcp"] } } }
```
A claude.ai custom connector needs a public HTTPS URL. See the README's "Connect from claude.ai"; it isn't needed for a local demo.

**Cursor.** Add this to `~/.cursor/mcp.json` and sign in when prompted:
```json
{ "mcpServers": { "opencg": { "url": "http://localhost:8181/mcp" } } }
```

**If a tool can't sign in, use a persona API key (dev only).** Run `DEMO_API_KEYS=1 make demo-seed`. One key per persona is written to `demo/.persona-keys` (mode 600, gitignored); they are never printed. Send a key as a header:
```json
{ "mcpServers": { "opencg-reader": { "url": "http://localhost:8181/mcp",
  "headers": { "Authorization": "Bearer <the demo-reader key from demo/.persona-keys>" } } } }
```

**Check the connection** before the audience arrives. Ask: *"Using opencg, what are the wire cut-off times?"* Every persona gets the same public answer from the *Juniper Bay Payments Wire and EFT Fees and Cut-off Times*.

**Switch persona:**
- with OAuth, sign out at `http://localhost:8380/realms/opencg/account` and authenticate the tool again;
- with API keys, configure one server entry per persona.

## 4. Demo scripts

Ask each question twice: first as `demo-reader`, then as the pack's persona. The two columns show what each should see. Every question is checked in CI on every pull request (`make demo-smoke`).

### Payments (persona `demo-payments-ops`)

| Question | `demo-payments-ops` sees | `demo-reader` sees |
|---|---|---|
| What amount triggers manual fraud review of an outgoing wire, and how many approvers does that review need? | CAD 50,000 threshold, two approvers, CAD 10,000 for high-risk countries | That a threshold exists and is set by the fraud team, with no figures |
| What fuzzy-match score sends a sanctions alert to Level 2 review? | 85 to Level 2; 70–84 Level 1; automatic hold at 95+ | The three alert levels, not the scores |
| Who must approve release of a held high-value payment during an incident, for example CAD 300,000? | Two approvers plus the Head of Payments Operations (CAD 250,000–999,999); the COO above CAD 1,000,000 | That approval depends on value, with no figures or roles |
| How many outgoing payments per hour trigger a velocity hold for a client? | Ten or more per hour | That velocity limits exist, with no figures |

### Wealth (persona `demo-advisor`)

| Question | `demo-advisor` sees | `demo-reader` sees |
|---|---|---|
| What household asset level makes a client high-net-worth, and what is the high-net-worth segment threshold? | CAD 1,000,000 in household investable assets and the segment table | That the threshold is in a confidential document |
| Who can approve a suitability exception, and what is the exception approval limit? | Approver bands from Branch Manager (up to CAD 50,000) to Head of Wealth (above CAD 1,000,000); 25% concentration; 12 months | That exceptions need approval and a register entry |
| How are advisor bonus tiers calculated, and does an upheld complaint affect the bonus? | Scorecard weights; 10/20/30% tiers; a one-tier reduction for an upheld complaint | That complaints may affect variable pay |

### Retail banking (persona `demo-branch`)

| Question | `demo-branch` sees | `demo-reader` sees |
|---|---|---|
| What credit score cut-off auto-declines a personal loan application? | 560 auto-decline; refer band 560–639; 42% TDS limit | That a cut-off exists in a confidential policy |
| When does an account move to external collections? | 120 days past due, unless hardship, complaint, dispute or vulnerability blocks it | That timings are in a confidential strategy |
| How much of a rate discount can a branch manager approve? | Up to 0.25 percentage points; above that goes to the District Manager | That approval levels depend on role |
| What is the maximum goodwill refund a card disputes team lead can approve? | Up to CAD 500 per case | That limits are held in a confidential document |

**Cross-pack:**
- Ask *"How does a wealth complaint relate to the group complaint standard?"* It retrieves the wealth procedure and the *Juniper Bay Group Complaint-Handling Standard* together.
- Ask any payments question as `demo-advisor` to show that domain roles don't cross.
- `demo-compliance` sees everything.

Each pack's `README.md` in `demo/packs/<pack>/` lists more public questions.

## 5. Show the trace, the audit and the cost

Open the admin UI at `http://localhost:3000` (or your `OPENCG__ADMIN_UI__HOST_PORT`) and sign in as a persona:
- **`/queries`** lists every retrieval. Open one to see its principal and roles, how many candidates retrieval found and how many were returned, and its tokens and estimated cost by provider. For a `demo-reader` query, fewer candidates are returned than found: OPA denied the confidential ones. Each candidate's decision, reason and policy revision is in the audit row's `candidate_decisions` (`GET /audit/{id}` on the pipeline).
- **`/graph`** shows the concepts and relationships extracted from the packs, with an Ollama Cloud key.
- **`/entities`** lists the documents. Filter by classification to see `confidential:payments` and the others.

With `make demo-up OBS=1`, Grafana at `http://localhost:3030` adds:
- **openCG / Pipeline stages**, with per-stage latency;
- **openCG / Tokens and cost**, with cost per provider and model;
- **openCG / Audit**, with audit writes per tool and outcome;
- Tempo, where you can open a trace by its correlation ID and follow one MCP call from the MCP server through the pipeline to the model call.

## 6. Reset

```bash
make demo-reset            # or PACK=wealth|payments|retail
make demo-seed             # brings the documents back
```

The reset tombstones the pack's documents, and the concepts first seen in them, through the API, so the tombstones are audited. Personas stay. `make down` stops the stack.

## Known limitations

- **The graph isn't filtered by entitlement yet** ([`add-graph-entitlement`](../ROADMAP.md#add-graph-entitlement)). `/graph` shows `demo-reader` the concepts extracted from confidential documents, though not the documents themselves. Don't show the graph as `demo-reader` until that ships.
- **Retrieval ranks by similarity.** If a scripted question misses its document, rephrase it with the distinctive terms from the table. CI checks every question as written.
- **Personas, API keys and the seeding commands are for `dev` only**, and refuse to run in any other environment.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `demo tooling runs only with OPENCG__ENVIRONMENT=dev` | Set `OPENCG__ENVIRONMENT=dev` in `.env` |
| `OPENCG__DEMO__PASSWORD is not set` | Copy the line from `.env.example` into `.env` |
| Persona sees no confidential content after an upgrade | Re-run `make demo-seed`. It restarts OPA so the demo domains load, and adds the demo roles to the `opencg` token scope |
| Tool sign-in fails or loops | Check `http://localhost:8380` is reachable and `OPENCG__KEYCLOAK__PUBLIC_URL` matches it; use a persona API key meanwhile |
| Graph is empty | Set `OPENCG__PROVIDERS__CHAT__API_KEY`, then re-run `make demo-seed` |
| Port already in use | Move it in `.env` (for example `OPENCG__ADMIN_UI__HOST_PORT`), then run `make demo-up` again |
