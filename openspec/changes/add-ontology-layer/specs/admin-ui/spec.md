## ADDED Requirements

### Requirement: Ontology page

The admin UI SHALL ship an `/ontology` route with three surfaces in one page: a **class tree** showing the hierarchy with each class's name, description, origin (`core` / `operator`), and count of concepts classified with it; a **constraint matrix** listing every relationship type with its `(domain, range)` pairs and an explicit marker for types that are unconstrained; and a **violations queue** listing edges whose `constraint_state` is `violation`, ordered so the most frequently violated relationship type surfaces first.

The class tree MUST support creating a child class, editing a class's name and description, reparenting a class, and deprecating a class. A reparent that would create a cycle MUST be reported inline with the server's error rather than silently reverted.

The constraint matrix MUST support adding and deleting constraints. Deleting a constraint MUST warn that edges currently marked `violation` under it will be re-evaluated.

Because the relationship vocabulary is now part of the ontology, the constraint matrix MUST also be where relationship types themselves are created, edited, and deprecated. There MUST NOT be a separate vocabulary page.

The violations queue MUST offer, per row, the same promote / edit / reject actions the existing candidate queue offers, plus a "reclassify endpoint" action that opens the concept's classification rather than editing the edge — because a violation is as often a mis-classified node as a wrong edge.

#### Scenario: Class tree renders the hierarchy

- **WHEN** an operator opens `/ontology`
- **THEN** the seeded core classes render as a tree with `Method` nested under `Function` under `CodeSymbol` under `Thing`

#### Scenario: Cycle error is reported inline

- **WHEN** an operator drags or edits a class so its parent becomes one of its own descendants
- **THEN** the page shows the server's cycle error next to the class
- **AND** the tree still reflects the unchanged server state

#### Scenario: Unconstrained relationship types are explicit

- **WHEN** an operator views the constraint matrix
- **THEN** `mentions`, `related_to`, `supersedes`, `causes`, and `derived_from` are each shown as explicitly unconstrained rather than omitted

#### Scenario: Violations queue offers reclassification

- **WHEN** an operator opens a row in the violations queue
- **THEN** an action is available to change the classification of the offending endpoint concept
- **AND** taking it re-evaluates the edge without changing the edge's review `state`

#### Scenario: Constraint deletion warns about re-evaluation

- **WHEN** an operator deletes a constraint that currently has edges marked `violation`
- **THEN** a confirmation names the number of edges that will be re-evaluated

#### Scenario: Relationship types are managed on the ontology page

- **WHEN** an operator adds a new relationship type
- **THEN** they do it from the constraint matrix on `/ontology`
- **AND** no separate vocabulary page exists in the admin nav

### Requirement: Class badges on existing concept surfaces

The existing concept browser, concept detail view, and candidate review queue SHALL display each concept's ontology class, and SHALL visually distinguish "unclassified" from any assigned class. The concept browser MUST offer a filter for unclassified concepts so the backlog is reachable without leaving the page.

#### Scenario: Unclassified concepts are visibly distinct

- **WHEN** an operator views a list containing both classified and unclassified concepts
- **THEN** the unclassified ones are marked as unclassified rather than shown with an empty or blank badge

#### Scenario: Backlog reachable from the concept browser

- **WHEN** an operator applies the unclassified filter in the concept browser
- **THEN** only concepts with no class are listed

### Requirement: Storybook coverage for ontology components

Every shared component introduced by the ontology page — at minimum `ClassTree`, `ClassBadge`, `ConstraintMatrix`, and `ViolationRow` — SHALL live in `src/components/` with a `*.stories.tsx` neighbour. Stories MUST cover the deprecated-class state, the unclassified state, and the unconstrained-relationship state, because those are the three cases a reader is most likely to render wrong.

#### Scenario: Each new component has stories

- **WHEN** the ontology page's components are added
- **THEN** each has a `*.stories.tsx` neighbour in `src/components/`

#### Scenario: Edge-case states are covered

- **WHEN** Storybook runs
- **THEN** stories exist for a deprecated class, an unclassified concept, and an unconstrained relationship type
