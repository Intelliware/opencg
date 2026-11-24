## ADDED Requirements

### Requirement: Estimated cost shown beside token usage

Every admin UI view that shows a request's token usage (the queries list, the audit detail page and the vector search result) SHALL also show its estimated cost in US dollars. The detail page and the vector search result SHALL also break usage down by provider and model. An unpriced provider MUST be labelled "unpriced", and rows written before cost was recorded MUST show "—". The cost components MUST have stories for the priced, partly unpriced and missing cases.

#### Scenario: Priced query shows its cost

- **WHEN** an operator opens `/queries/<id>` for a retrieval made with the default price table
- **THEN** the page shows the token counts, the estimated cost in US dollars and one breakdown row per provider and model used

#### Scenario: Queries list shows cost per row

- **WHEN** an operator opens `/queries`
- **THEN** each row shows an estimated cost next to its token counts

#### Scenario: Unpriced provider is labelled

- **WHEN** a retrieval used a provider and model with no price entry
- **THEN** its detail page labels that breakdown row "unpriced"
- **AND** the total is marked as excluding unpriced usage

#### Scenario: Older audit rows

- **WHEN** an operator opens an audit row written before cost was recorded
- **THEN** the cost is shown as "—" and the page renders without errors

#### Scenario: Vector search shows cost

- **WHEN** an operator runs a search on `/vectors`
- **THEN** the result shows the query's embedding tokens, provider, model and estimated cost
