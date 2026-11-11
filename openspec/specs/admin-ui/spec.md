# Admin UI

## Purpose

Provide operators with review and management surfaces for vectors, catalogue entities, ingestion, and retrieval activity.

## Requirements

### Requirement: Vector neighbourhood exploration

The admin UI SHALL expose a vector search surface at `/vectors`. Operators MUST be able to enter free-text and receive the top-K nearest catalog entities ordered by score, with `entity_id`, `source`, `source_uri`, `title`, `classification`, a text snippet, and the model + provider used. From any result the operator MUST be able to drill into "show neighbours of this entity" which re-runs the search keyed on the entity's stored vector.

The page MUST display the currently configured embedding model + dimension in a small status header so operators recognise which index they are searching.

#### Scenario: Free-text vector search

- **WHEN** an operator submits a query string with `top_k = 20`
- **THEN** the page calls `POST /search/vector` on the pipeline and renders an ordered list of up to 20 hits with the required fields
- **AND** each hit shows the score formatted to four decimal places

#### Scenario: Show neighbours of an entity

- **WHEN** an operator clicks "show neighbours" on a hit for `entity_id = E1`
- **THEN** the page calls `POST /search/vector` with the stored vector keyed on `E1` (or, in v0+1, re-embeds the entity's text)
- **AND** the first hit is `E1` itself with the highest score

#### Scenario: Status header reflects active model

- **WHEN** the page loads
- **THEN** the status header shows `embedding_model` and `vector_size` sourced from `GET /readyz` or a dedicated `/config` endpoint on the pipeline

### Requirement: Content management

The admin UI SHALL expose an entity browser at `/entities` and an entity detail page at `/entities/[id]`. The browser MUST support filtering by `source`, `classification`, and `freshness_state`, and MUST paginate with `limit` and `offset`. The detail page MUST show entity title, `source`, `source_uri`, `classification`, `freshness_state`, `last_verified_at`, `content_hash`, metadata JSON, lineage (parent entity if present + listing of chunks if this is a parent), the body text (first 50 KB with a "show full" toggle), and the audit appearances of this entity in the last N retrievals.

The detail page MUST expose a "Tombstone" action that posts `DELETE /entities/{id}` to the pipeline. Tombstoned entities MUST render with a visible banner indicating their state and the tombstone timestamp.

#### Scenario: Browse entities by source

- **WHEN** an operator filters the entity browser by `source=git, classification=internal`
- **THEN** the response calls `GET /entities?source=git&classification=internal&limit=50&offset=0`
- **AND** the list renders the returned rows with `title`, `source_uri`, `classification`, `freshness_state`, and `updated_at`

#### Scenario: Inspect entity detail

- **WHEN** an operator opens `/entities/{id}`
- **THEN** the page shows the required fields and the lineage block
- **AND** the body section is collapsed to the first 50 KB with a "Show full body" toggle that fetches the rest

#### Scenario: Tombstone an entity

- **WHEN** an operator confirms the tombstone dialog for `entity_id = E1`
- **THEN** the page issues `DELETE /entities/E1` to the pipeline
- **AND** on success the page shows a "Tombstoned at …" banner
- **AND** subsequent calls to `GET /entities/E1` return the entity with a non-null `tombstoned_at`

### Requirement: Content ingestion control

The admin UI SHALL expose `/ingestion`. The page MUST list configured connectors with `name`, `supported`, `last_run_at`, `last_run_status`, `last_run_error` if any, and recent runs (last 20) with `started_at`, `finished_at`, `status`, `parents`, `chunks`, and `error`. The page MUST include a "Run now" form for the git connector accepting a `repo_url` field, which POSTs `/ingestion/git/run` to the pipeline.

#### Scenario: Trigger a git ingest from the UI

- **WHEN** an operator submits `repo_url = https://github.com/<owner>/<repo>` in the Run-now form
- **THEN** the UI calls `POST /ingestion/git/run` and renders a row in the recent-runs list for the new run with `status = queued` or `status = running`
- **AND** the row updates to `succeeded` (with `parents` and `chunks` counts) or `failed` (with `error`) as the run completes

#### Scenario: Connector listing surfaces deferred connectors

- **WHEN** the page renders the connector list
- **THEN** the git connector appears with `supported = true`
- **AND** the deferred connectors (`confluence`, `custom-api`, `web`) appear with `supported = false` and a `Reason` tooltip naming the follow-up change

### Requirement: Graph relationship management

The admin UI SHALL expose a graph management surface at `/graph` containing three sub-views:

1. **Concept browser** — filter by `state` (default: `confirmed,candidate`), free-text name search, paginated list with `state` badge, `aliases`, last `updated_at`. Clicking a row opens the concept detail.
2. **Concept detail** — header with the concept name and editable description + aliases; "Tombstone" and "Merge into…" actions; two neighbour tables (confirmed + candidate) each listing the edge `type`, peer concept name, `confidence`, and the evidence chunk(s). Per-edge actions: promote, demote, edit type, delete.
3. **Candidate review queue** — paginated list of `candidate` edges ordered by `confidence DESC`. Per-row actions: promote, demote, edit type, delete. Each row links the edge to its evidence chunk via the existing `/entities/[id]` page.

A small "Vocabulary" panel within `/graph` lists relationship types from the API; admins can add a new type, edit its `description`, or mark it deprecated. The UI MUST NOT include a visual graph rendering in this change (tabular only — visual rendering is a follow-up).

Storybook coverage is mandatory for every new component (`ConceptRow`, `ConceptDetail`, `CandidateEdgeRow`, `RelationshipTypeBadge`, `VocabRow`).

#### Scenario: Concept browser default filter

- **WHEN** an operator navigates to `/graph` with no query parameters
- **THEN** the page renders the concept browser with `state = confirmed,candidate`, no search filter, `limit = 50`
- **AND** the page calls `GET /graph/concepts?state=confirmed,candidate&limit=50&offset=0`

#### Scenario: Candidate review queue lists by confidence

- **WHEN** an operator opens the candidate review queue tab
- **THEN** the page calls `GET /graph/edges?state=candidate&limit=50`
- **AND** rows render ordered by `confidence DESC`

#### Scenario: Promote a candidate edge from the review queue

- **WHEN** an operator clicks "Promote" on a row in the candidate review queue
- **THEN** the UI posts `/graph/edges/{id}/promote` with the reason field
- **AND** on success the row is removed from the queue
- **AND** a "promoted" toast appears

#### Scenario: Edit a vocabulary entry's description

- **WHEN** an admin edits the description of `depends_on` in the vocabulary panel
- **THEN** the UI patches `/graph/vocab/depends_on`
- **AND** subsequent reads show the new description

#### Scenario: Storybook covers the new components

- **WHEN** `pnpm --filter @opencg/admin-ui build-storybook` is run after this change ships
- **THEN** at least one story exists for each of `ConceptRow`, `ConceptDetail`, `CandidateEdgeRow`, `RelationshipTypeBadge`, `VocabRow`
- **AND** Storybook builds without warnings

### Requirement: Storybook coverage for every new component

Every new shared component introduced by this capability (`EntityRow`, `EntityDetail`, `VectorHit`, `ConnectorCard`, `IngestionRunRow`) MUST have a neighbour `*.stories.tsx` file with at least three stories covering the canonical, empty, and error states.

#### Scenario: Stories exist alongside components

- **WHEN** the components above are added under `services/admin-ui/src/components/`
- **THEN** each component has a `<Name>.stories.tsx` neighbour file in the same directory
- **AND** Storybook builds without error under `pnpm --filter @opencg/admin-ui build-storybook`

### Requirement: Design system and styling conventions

The admin UI SHALL use Tailwind CSS (v3.4, `darkMode: "class"`) as its styling system, with shadcn/ui primitives vendored under `src/components/ui/` and Tremor (`@tremor/react`) for all chart and KPI visuals. Authored app code MUST NOT use inline `style={{...}}` objects for visual styling (dynamic values such as computed bar widths are exempt) and MUST NOT import `recharts` directly. Theme colours MUST be expressed through the shared CSS-variable tokens defined in `globals.css` so both themes resolve correctly.

Vendored files under `src/components/ui/**` are exempt from the `*.stories.tsx` neighbour rule; every authored component directly in `src/components/` retains it.

#### Scenario: No inline styles remain in authored code

- **WHEN** `grep -rn "style={{" services/admin-ui/src/app services/admin-ui/src/components --include "*.tsx"` is run after this change ships, excluding `src/components/ui/`
- **THEN** the only matches (if any) are dynamic computed values (e.g., percentage widths), not static visual styling

#### Scenario: Charts use Tremor only

- **WHEN** `grep -rn "from \"recharts\"" services/admin-ui/src` is run
- **THEN** there are no matches in authored app code

### Requirement: Dark and light themes with a persistent toggle

The admin UI SHALL support light and dark themes via `next-themes` (class strategy), defaulting to the operator's system preference and persisting an explicit choice across sessions. A theme toggle MUST be reachable from every page via the app shell. Every authored component and every vendored primitive in use MUST render legibly in both themes.

#### Scenario: Default follows system preference

- **WHEN** an operator with OS-level dark mode visits any admin UI page with no stored preference
- **THEN** the page renders with the dark theme (`dark` class on the document element) without a flash of the wrong theme

#### Scenario: Explicit choice persists

- **WHEN** an operator clicks the theme toggle to switch from dark to light and then reloads the page
- **THEN** the page renders with the light theme

### Requirement: App shell with sidebar navigation

The admin UI SHALL present a persistent left sidebar containing the product name, navigation links in the order **Overview, Graph, Vectors, Entities, Queries, Ingestion**, each with a lucide icon, an active-route highlight, and the theme toggle. On narrow viewports the sidebar SHALL collapse into a toggleable drawer. The previous inline-styled horizontal header is removed.

#### Scenario: Navigation links appear in the defined order

- **WHEN** the sidebar renders
- **THEN** its navigation links appear top-to-bottom as Overview, Graph, Vectors, Entities, Queries, Ingestion

#### Scenario: Active route is highlighted

- **WHEN** an operator is on `/entities`
- **THEN** the sidebar renders the Entities item in its active state and all other items in their inactive state

#### Scenario: Sidebar collapses on narrow viewports

- **WHEN** the viewport is narrower than the configured breakpoint
- **THEN** the sidebar is hidden behind a menu button that opens it as a drawer

### Requirement: Overview dashboard at /

The admin UI home page SHALL be an overview dashboard composed exclusively from existing pipeline read endpoints (no new API surface): a row of `StatCard`s (recent query count, entity total, candidate-edge count, supported-connector count), a `BreakdownCard` containing a Tremor chart of recent query activity derived from `/audit/recent`, and a `RankedList` of top sources by entity count. If a value is not derivable from existing endpoints the corresponding card is omitted.

#### Scenario: Dashboard renders from existing endpoints

- **WHEN** an operator opens `/` with the stack running
- **THEN** the page issues reads only to existing endpoints (audit, entities, graph edges, ingestion connectors) via the existing proxy pattern
- **AND** stat cards, the activity chart, and the ranked list render with live values

#### Scenario: Dashboard degrades gracefully

- **WHEN** one of the underlying reads fails
- **THEN** the affected card renders an error/empty state
- **AND** the remaining cards render normally

### Requirement: Authored dashboard components with stories

The admin UI SHALL provide four new authored components, each with a `*.stories.tsx` neighbour covering both themes: `StatCard` (label, value, optional delta and sparkline), `RankedList` (top-N rows with proportional value bars), `FilterChipBar` (toggleable chips that drive URL query parameters), and `BreakdownCard` (titled card wrapping a Tremor chart with legend).

#### Scenario: Stories exist for the new components

- **WHEN** `pnpm --filter @opencg/admin-ui build-storybook` is run after this change ships
- **THEN** at least one story exists for each of `StatCard`, `RankedList`, `FilterChipBar`, `BreakdownCard`
- **AND** the Storybook build completes without errors

### Requirement: Storybook theme switching

The Storybook instance SHALL compile Tailwind styles and provide a global toolbar control that switches stories between light and dark themes by toggling the `dark` class, replacing the previous hard-coded background presets.

#### Scenario: A story is viewable in both themes

- **WHEN** a reviewer opens any component story and flips the theme toolbar control
- **THEN** the story re-renders with the selected theme's tokens applied

### Requirement: Existing pages and components restyled without behavioural change

All existing routes (`/`, `/queries`, `/queries/[id]`, `/entities`, `/entities/[id]`, `/ingestion`, `/vectors`, `/graph`) and all 17 existing authored components SHALL be restyled with Tailwind + kit primitives. Data fetching, proxy routes, URL parameters, filters, pagination, and actions MUST behave identically to before this change; vitest suites MUST pass unmodified except for assertions that targeted inline styles or class names.

#### Scenario: Graph review workflow unchanged

- **WHEN** an operator promotes a candidate edge from the restyled `/graph` review queue
- **THEN** the UI posts `/graph/edges/{id}/promote` with a reason, removes the row on success, and shows a confirmation toast, exactly as specified in `add-knowledge-graph`

#### Scenario: Entity filters unchanged

- **WHEN** an operator applies source and classification filters on the restyled `/entities` page
- **THEN** the same query parameters are sent to the same proxy route as before this change

### Requirement: Interactive graph exploration view

The `/graph` page SHALL provide a force-directed graph exploration view ("Map" tab) that renders concepts as nodes and relationships as edges, seeded from a focused concept and expandable by navigation. The Map view SHALL be the **default** view of the `/graph` page when no `tab` query parameter is given. The view SHALL consume the existing `GET /graph/traverse` endpoint via the graph proxy and MUST NOT require any new pipeline route, schema, or wire-type change. The existing Concepts, Candidate review, and Vocabulary tabs and their behaviour MUST remain unchanged and reachable.

#### Scenario: Map is the default graph view

- **WHEN** an operator opens `/graph` with no `tab` query parameter
- **THEN** the Map view is rendered (seeded from a default concept) rather than the Concepts list, while the Concepts, Candidate review, and Vocabulary tabs remain reachable via their tab links

#### Scenario: Map tab renders the focused neighbourhood

- **WHEN** an operator opens `/graph?tab=map` with a `focus` concept id (or a default seed when none is given)
- **THEN** the client calls `GET /graph/traverse` for that concept and renders the returned `nodes` as a force-directed layout with `edges` drawn between them, labelled relationship by type

#### Scenario: Clicking a node re-centers the graph and opens its detail

- **WHEN** an operator clicks a node in the Map view
- **THEN** that concept becomes the new focus (reflected in the URL query), the traversal is refetched and re-rendered around it, AND the concept's detail card is shown, so the operator can both walk the graph node by node and inspect the selected concept

#### Scenario: Obsidian-style interaction

- **WHEN** an operator interacts with the Map canvas
- **THEN** the layout settles via force simulation, nodes can be dragged, the canvas can be panned and zoomed, the view fits the current neighbourhood after a refocus, and hovering a node spotlights its local cluster

#### Scenario: Core nodes are always labelled

- **WHEN** the Map view renders any neighbourhood
- **THEN** the focused node and "core" nodes (degree at or above the core threshold) display their concept name label at all times

#### Scenario: A selected node's neighbours are labelled

- **WHEN** an operator selects or hovers a node
- **THEN** that node and its directly connected neighbour nodes display their name labels, and the labelling updates dynamically as the selection, hover, or zoom changes

#### Scenario: Candidate inclusion is toggleable and visually distinct

- **WHEN** an operator toggles "include candidates"
- **THEN** the traversal is refetched with `include_candidates` set accordingly, and candidate concepts/edges are rendered with a visually distinct style (e.g. amber / dashed) from confirmed ones in both light and dark themes

#### Scenario: Empty or unreachable graph degrades gracefully

- **WHEN** there is no concept to focus on, or the traverse request fails or returns no nodes
- **THEN** the Map view shows a clear empty/error state (e.g. a prompt to pick a concept) instead of a blank canvas or an unhandled error

### Requirement: Map concept search

The Map view SHALL provide a concept search control in its toolbar so an operator can jump to any concept without clicking through the graph. The control MUST query the existing `GET /graph/concepts?search=` endpoint (debounced) via the graph proxy and MUST NOT require any new pipeline route or wire-type change. Selecting a result SHALL make that concept the focus — refetching the traversal, re-centering the graph, and loading its detail — exactly as clicking a node does.

#### Scenario: Searching lists matching concepts

- **WHEN** an operator types into the Map search box
- **THEN** the client issues a debounced `GET /graph/concepts?search=<query>` request and renders the matches as a results list showing each concept's name and state

#### Scenario: Selecting a search result focuses the graph

- **WHEN** an operator chooses a concept from the search results
- **THEN** that concept becomes the focus (reflected in the URL query), the traversal is refetched and re-centered around it, and its detail panel loads

#### Scenario: No matches degrades gracefully

- **WHEN** the search query returns no concepts
- **THEN** the control shows a clear empty-results state and the current graph and detail panel are left unchanged

### Requirement: Map detail panel content and navigation

The Map detail panel SHALL present the selected concept with a readable, information-rich layout sourced from the existing `GET /graph/concepts/{id}` (`ConceptDetail`) payload, and MUST NOT require a new pipeline route or wire-type change. The panel MUST show the concept name, state, and description, a metadata block (aliases, a link to the source entity when `source_entity_id` is present, and neighbour degree), and a footer with `extractor_version` and creation date when present. Confirmed and candidate neighbours MUST be presented under a segmented Confirmed/Candidate switch with per-group counts.

Each neighbour MUST be rendered by its **peer concept name** (from `Neighbour.peer`), never a raw concept UUID, alongside its relationship type, confidence, and evidence link(s) to the supporting entities. Selecting a neighbour SHALL re-focus the graph on that peer concept, so the operator can walk the graph from the panel.

Concept-level review actions (promote, demote, merge, tombstone) SHALL be available from an actions menu in the panel header. The panel MUST NOT render per-neighbour promote/demote/edit/delete controls; that candidate-edge review workflow remains on the Candidate review tab and is unchanged.

#### Scenario: Neighbours show names, not UUIDs

- **WHEN** the detail panel renders a concept that has confirmed or candidate neighbours
- **THEN** each neighbour row displays the peer concept's name, its relationship type, its confidence, and evidence link(s), and no raw concept UUID is shown

#### Scenario: Selecting a neighbour navigates the graph

- **WHEN** an operator selects a neighbour in the detail panel
- **THEN** the peer concept becomes the new focus, the traversal is refetched and re-centered around it, and the detail panel updates to that peer

#### Scenario: Confirmed and candidate neighbours are segmented

- **WHEN** a concept has both confirmed and candidate neighbours
- **THEN** the panel shows a Confirmed/Candidate switch with each group's count, and the selected group's neighbours are listed

#### Scenario: Concept actions are available without per-neighbour controls

- **WHEN** an operator opens the detail panel's actions menu
- **THEN** promote, demote, merge, and tombstone actions for the selected concept are available, AND no neighbour row exposes promote/demote/edit/delete controls

### Requirement: Graph page tab order

The `/graph` page's tab bar SHALL list its tabs in the order **Map, Concepts, Candidate review, Vocabulary**, so the Map (the default view) is the first tab. Reordering the tab bar MUST NOT change which view is the default for `/graph` with no `tab` query parameter (Map remains the default).

#### Scenario: Map is the first graph tab

- **WHEN** an operator opens the `/graph` page
- **THEN** the tab bar lists Map first, followed by Concepts, Candidate review, and Vocabulary
- **AND** opening `/graph` with no `tab` query parameter still renders the Map view by default

### Requirement: End-to-end browser test suite

The admin UI SHALL have a Playwright end-to-end suite under `services/admin-ui/e2e/` that drives every route in a real browser against the running compose stack. The suite MUST seed its own data from the committed smoke fixture with a unique run identifier, and every assertion and mutation MUST target only entities, candidate relationships and vocabulary entries created by the current run. The suite MUST be runnable with `make e2e` and MUST NOT call an external chat provider.

#### Scenario: Every route renders against live services

- **WHEN** `make e2e` runs against a healthy stack
- **THEN** `/`, `/queries`, `/queries/[id]`, `/vectors`, `/entities`, `/entities/[id]`, `/ingestion` and `/graph` each load without an error boundary, an uncaught console error or a failed same-origin request
- **AND** sidebar navigation reaches each page

#### Scenario: Vector search finds seeded content

- **WHEN** the test searches `/vectors` for the fixture's unique retrieval phrase
- **THEN** a result from the current run's `source_uri` prefix appears with a score and snippet

#### Scenario: Retrieval appears in the query log

- **WHEN** the test issues a retrieval through the pipeline and then opens `/queries`
- **THEN** a row with the test's correlation ID is listed
- **AND** its detail page shows token counts and fragments

#### Scenario: Entity browse, detail and tombstone

- **WHEN** the test filters `/entities` to the current run, opens a chunk and confirms the tombstone action
- **THEN** the detail page shows the entity as tombstoned
- **AND** a subsequent vector search no longer returns that chunk

#### Scenario: Ingestion run from the UI

- **WHEN** the test submits the "Run now" form on `/ingestion` with the run's local fixture repository
- **THEN** a new run appears in the run list and reaches a terminal success state within the suite timeout

#### Scenario: Graph review flows

- **WHEN** the test searches a fixture concept on `/graph`, opens its detail, promotes one current-run candidate relationship, rejects another and adds a vocabulary entry
- **THEN** each change is reflected in the UI after reload
- **AND** no candidate or vocabulary entry outside the current run is modified

#### Scenario: Theme toggle persists

- **WHEN** the test switches the theme and reloads
- **THEN** the selected theme is still applied

#### Scenario: Failures leave evidence

- **WHEN** an e2e test fails in CI
- **THEN** the Playwright HTML report, trace and screenshot are uploaded as build artifacts

### Requirement: Clean-checkout build

The admin UI's production image, `next build`, `tsc --noEmit`, the ESLint CLI (`pnpm lint`) and `build-storybook` SHALL all succeed from a clean checkout with no untracked files, and none of them MAY prompt for interactive input.

#### Scenario: Storybook builds from a clean clone

- **WHEN** a contributor clones the repo, runs `make bootstrap` and then `pnpm --filter @opencg/admin-ui build-storybook`
- **THEN** the build exits 0

#### Scenario: Lint is non-interactive

- **WHEN** `pnpm --filter @opencg/admin-ui lint` runs in a non-TTY environment
- **THEN** it uses the committed ESLint configuration and exits without prompting

### Requirement: Optional admin access gate

When `OPENCG__ADMIN_UI__PASSWORD` is set, the admin UI SHALL require an authenticated session for every page and every `/api/proxy/**` route. When it is unset, the UI MUST display a persistent unauthenticated-mode banner and log a startup warning. The gate is a stopgap and MUST be marked `REPLACE-BEFORE-PROD` in source.

#### Scenario: Gate blocks unauthenticated proxy calls

- **WHEN** the password is set and a request without a session calls `DELETE /api/proxy/entities/<id>`
- **THEN** the response is 401 and no request reaches the pipeline

#### Scenario: Login grants access

- **WHEN** the password is set and the user submits the correct password at `/login`
- **THEN** they are redirected to the page they requested and can use it

#### Scenario: Unauthenticated mode is visible

- **WHEN** the password is unset
- **THEN** every page shows the unauthenticated-mode banner
