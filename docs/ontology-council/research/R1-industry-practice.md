# R1 — Industry dossier: what "ontology" means in shipping systems, and what it actually does

**Model:** GPT-5.6 sol @ max
**Research cut:** public documentation, engineering posts, papers, APIs, and issue trackers reviewed through 7 August 2026.

## Executive finding

"Ontology" is not one industry concept.

1. **W3C tradition** — formally defined classes, properties, individuals, and axioms that software reasons over. Validation is a separate concern handled by SHACL. ([OWL 2](https://www.w3.org/TR/owl-overview/), [SHACL](https://www.w3.org/TR/shacl/))
2. **Property-graph products** — node labels, relationship types, properties, endpoint patterns, optional database constraints. ([Neo4j](https://neo4j.com/docs/getting-started/appendix/graphdb-concepts/), [TigerGraph](https://docs.tigergraph.com/gsql-ref/3.10/ddl-and-loading/defining-a-graph-schema))
3. **Data catalogs** — a governed vocabulary attached to assets: glossary terms, classifications, domains, owners, term-to-term relations. Rarely constrains source data. ([DataHub](https://docs.datahub.com/docs/glossary/business-glossary), [Atlan](https://docs.atlan.com/product/capabilities/governance/glossary/concepts/what-is-a-glossary))
4. **Semantic layers** — executable definitions of metrics, dimensions, entities, joins, access policies. Often avoid the word "ontology," but their semantics are more load-bearing than most business glossaries. ([dbt MetricFlow](https://docs.getdbt.com/docs/build/about-metricflow), [LookML](https://docs.cloud.google.com/looker/docs/what-is-lookml), [Cube](https://docs.cube.dev/docs/introduction))
5. **LLM graph builders** — a whitelist or structured-output schema supplied to an extraction model, followed—sometimes—by deterministic filtering. ([LlamaIndex](https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide), [LangChain](https://reference.langchain.com/python/langchain-neo4j/graph_transformers/llm/LLMGraphTransformer))
6. **Loose usage** — some products call an automatically inferred entity graph an ontology even though users cannot define its types or constraints. Glean, Mem0, Sana. ([Glean](https://www.glean.com/enterprise-context/enterprise-graph), [Mem0](https://docs.mem0.ai/platform/features/graph-memory), [Sana](https://sanalabs.com/the-bitter-lessons))

**The durable distinction is not "has ontology / lacks ontology." It is:**

- Does it change extraction?
- Does it change query planning, filtering, traversal, or ranking?
- Does it infer additional facts?
- Does it reject invalid writes?
- Does it govern who may perform an action?
- Or is it only documentation?

## Evidence labels

- **Enforced:** software rejects an invalid write or prevents an operation.
- **Validated:** software reports non-conformance; rejection may be optional.
- **Advisory:** guides a human, model, compiler, or UI but is not a database constraint.
- **Inferred:** types or links assigned probabilistically or by rules.
- **Not verified:** public material insufficient.
- **Vendor claim:** asserted but not independently demonstrated.

---

# 1. Palantir Foundry / AIP Ontology

### What is typed?

Object types define business nouns; properties have base types; link types connect object types; interfaces define common required/optional properties, links, and actions; action types and functions define operations. Palantir describes the combination as **semantic** elements (objects, properties, links) and **kinetic** elements (actions, functions, dynamic security). ([Overview](https://palantir.com/docs/foundry/ontology/overview/), [interfaces](https://palantir.com/docs/foundry/interfaces/create-interface/), [Ontology system](https://palantir.com/docs/foundry/architecture-center/ontology-system/))

Links are not free-form predicates. Interface link constraints specify target object/interface, cardinality, and whether implementation is required. Required interface properties must be mapped by every implementing object type. ([Interface link types](https://palantir.com/docs/foundry/interfaces/interface-link-types-overview/))

### Is the schema load-bearing?

**Yes, extensively.**

- Object Explorer queries typed object sets and traverses links through "Search Arounds," then applies bulk actions. ([Applications](https://palantir.com/docs/foundry/ontology/applications/))
- The Ontology SDK generates language-level types and query functions from the selected ontology subset. ([OSDK](https://palantir.com/docs/foundry/ontology-sdk/overview/))
- Property base types constrain available operations; interfaces provide polymorphism.
- Actions perform controlled edits or external writeback, not annotation. ([Object backend](https://palantir.com/docs/foundry/object-backend/overview/))

### Who authors and maintains it?

Ontology Manager is the visual authoring app, with working state, branches, resource search, usage inspection, history, restoration. Ontologies may alternatively be declared as code in a SuperRepo. ([Ontology Manager](https://palantir.com/docs/foundry/ontology-manager/overview/))

Breaking object-schema changes create a new schema version and replacement indexing pipeline. Object Storage v2 detects breaking changes and offers predefined migrations for existing user edits. Interface docs recommend versioning an interface if consumers cannot migrate atomically. ([Schema migrations](https://palantir.com/docs/foundry/object-edits/schema-migrations/))

### Enforced, advisory, or inferred?

All three, but the important operational parts are **enforced**.

- Required interface mappings and compatible property/link definitions are enforced on save.
- **Action submission criteria are hard runtime gates.** They inspect the current user, action parameters, objects, and related objects; an action cannot run unless every criterion passes. ([Submission criteria](https://palantir.com/docs/foundry/action-types/submission-criteria/))
- Applying an action also requires access to affected object/link types and backing data. ([Action permissions](https://palantir.com/docs/foundry/action-types/permissions/))
- Display names and descriptions remain descriptive.

### Interaction with LLMs in AIP

AIP does not merely paste ontology descriptions into a prompt.

- AIP Analyst searches the ontology for relevant object types, creates object sets, applies typed filters and transformations, then summarizes. ([AIP Analyst](https://palantir.com/docs/foundry/aip-analyst/overview/))
- Chatbot Studio exposes selected ontology data, functions, and actions as agent tools.
- **Tool invocation is evaluated through the same permissions and submission criteria as human use.** ([Securing agents](https://blog.palantir.com/securing-agents-in-production-agentic-runtime-1-5191a0715240))
- AI FDE can propose ontology edits through branches or pull requests for review rather than mutating production definitions invisibly. ([AI FDE](https://palantir.com/docs/foundry/ai-fde/overview/))

Claims about organization-wide decision quality and deployment outcomes remain **vendor claims**.

---

# 2. Enterprise search and AI assistants

## Glean

**Typed:** content, people, activity. Custom connectors provide an `objectType`; datasource `objectDefinitions` contain typed custom properties (`TEXT`, `PICKLIST`, `DATE`, `INT`, `USERID`). **No customer-authored domain/range ontology for inferred graph edges.** ([Knowledge Graph](https://docs.glean.com/security/knowledge-graph), [custom properties](https://developers.glean.com/api-info/indexing/datasource/custom-properties))

**Load-bearing:** yes, as search metadata rather than formal ontology. Object types control presentation and become facets; custom properties can be searchable, filterable, faceted, displayed, and used as ranking signals; ownership, organizational proximity, link structure, recency, and activity feed ranking; mirrored ACLs filter at query time. ([Security principles](https://docs.glean.com/security/security-principles))

**Maintenance:** connector developers and administrators map source objects, fields, permissions, display. ML infers identities and graph signals. Custom properties require full document re-upload when changed; the separate Custom Metadata API permits independent schema and value updates. **No public documentation of graph-wide type migrations or deterministic retyping.**

**Enforcement:** custom metadata payloads must conform to configured property schemas; ACL enforcement is hard at retrieval. Entity resolution and organizational relationships are largely **inferred**. Object types influence filtering and ranking but do not document valid source/target relationship combinations.

## Dashworks

No public customer-authored ontology or graph schema found. Documented load-bearing mechanisms are connector-specific real-time searches, relevance, authority, recency, metadata, citations, source permissions — **not ontology traversal**. Source applications remain systems of record; Dashworks calls their APIs at query time. ([Privacy-first architecture](https://www.dashworks.ai/blog/privacy-first-enterprise-search-why-dash-ai-ditched-indexing))

## Sana

Publicly **claims** it derives a knowledge graph for structured, multi-variable questions (e.g. filtering companies by revenue, meeting location, time). Public API exposes application entities but not a configurable search ontology. **Public material does not reveal the query planner, graph schema, traversal algorithm, or any evaluation.** Treat as vendor claim with insufficient detail. ([Bitter Lessons](https://sanalabs.com/the-bitter-lessons))

## Elastic

**Typed:** fields, not business entities. Elasticsearch removed document mapping types in 7.0 — **this is not a node-class ontology.** ([Mapping](https://www.elastic.co/guide/en/elasticsearch/reference/8.19/mapping.html))

**Load-bearing:** very much so. Field types determine analysis, filtering, sorting, aggregation, vector inference, query operators. `semantic_text` generates embeddings and selects the inference endpoint; hybrid retrieval combines semantic and lexical via RRF.

**Elastic's own engineering account found pure semantic retrieval inferior to BM25 plus semantic filtering for one deployment.** ([Semantic search as a service](https://www.elastic.co/search-labs/blog/semantic-search-as-service-at-a-search-center-of-excellence))

**Enforcement:** mapping can be inferred or hard. Default dynamically creates fields; `dynamic: false` ignores unknown fields; `dynamic: strict` **rejects the entire document**. Wrong datatypes reject documents unless `ignore_malformed`. ([Dynamic mapping](https://www.elastic.co/guide/en/elasticsearch/reference/8.19/dynamic.html))

**Enterprise-search pattern:** Glean is the strongest public example of graph-informed ranking, but even it combines the graph with embeddings, lexical retrieval, permissions, and behavioral signals. Dashworks and Elastic show strong enterprise retrieval can ship **without** a formal ontology.

---

# 3. Knowledge graph platforms

**One-sentence contrast:** property-graph products make types native database labels and relationship types with optional closed-world constraints; RDF/OWL products make classes and properties part of the graph and use them for semantic inference, with SHACL supplying separate closed-world validation.

## Neo4j

**Typed:** nodes may have zero or more labels; every relationship has exactly one type and a direction; both may have properties.

**Load-bearing:** labels and relationship types are used directly in Cypher matching and indexes. Constraints enforce property uniqueness, existence, datatype, keys. Cypher 25 "graph types" describes a holistic open schema. ([Constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/), [graph types](https://neo4j.com/docs/cypher-manual/current/schema/graph-types/))

Neo4j's GraphRAG builder separately uses a `GraphSchema` to guide LLM entity/relation extraction — manually supplied or extracted once by an LLM and reused for all chunks. **That guiding schema is not a database constraint.** ([KG builder](https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_kg_builder.html))

**Enforcement:** constraint creation scans existing data and fails if the current graph conflicts. Graph types was introduced in Neo4j 2026.02 as an Enterprise/Cypher 25 **preview intended only for internal development** — not mature baseline behavior.

## TigerGraph

**Typed:** vertices have declared types, primary IDs, typed attributes. Edges have declared types, directionality, attributes, and **allowed `FROM`/`TO` vertex-type pairs.** ([Schema](https://docs.tigergraph.com/gsql-ref/3.10/ddl-and-loading/defining-a-graph-schema))

**Load-bearing / enforced:** load jobs must name declared vertex and edge types; dynamic endpoint types must resolve to an allowed source/target type. GSQL queries are compiled against the schema. A change that drops or alters a referenced type **invalidates loading jobs and queries**; invalid jobs are dropped or uninstalled and must be rebuilt. TigerGraph cautions against frequent production schema changes. ([Modifying a schema](https://docs.tigergraph.com/gsql-ref/4.1/ddl-and-loading/modifying-a-graph-schema))

## Stardog

**Typed:** RDF resources can have one or more `rdf:type` classes. RDFS/OWL define classes, properties, hierarchies, **domains/ranges**, equivalence, rules. SHACL separately defines closed-world structural constraints.

**Load-bearing in two distinct ways:**
- With reasoning enabled, Stardog rewrites queries against RDFS/OWL axioms and user rules; queries return **inferred** types and relationships not explicitly stored. ([Inference engine](https://docs.stardog.com/inference-engine/))
- SHACL validation produces concrete violation reports. With **"guard mode"** enabled, a transaction that violates constraints **fails**. ([Data-quality constraints](https://docs.stardog.com/data-quality-constraints))

**Critical semantics:** OWL/RDFS is primarily **inferential and open-world**; a domain/range axiom typically **implies types rather than acting like a SQL foreign-key rejection.** SHACL is validation; guard mode turns it into write-time enforcement. ([SHACL vs OWL](https://spinrdf.org/shacl-and-owl.html))

## TerminusDB

**Typed:** JSON documents instantiate named classes. Class schemas define scalar properties, links, inheritance, keys, enums, list/set/array families, cardinality.

**Enforced:** branch graphs maintain a schema and perform a schema check during update transactions. Schema checking is **enforced by default**; it can be disabled for schemaless operation but **cannot be re-enabled until all documents conform.** Schema and instance data are versioned together with Git-like commits, branches, merges, time travel. Schema migrations are ordered, replayable operations. ([Schema migration](https://terminusdb.com/docs/schema-migration-reference-guide/))

## Ontotext GraphDB

**Typed:** RDF/RDFS/OWL — subclassing, equivalence, inverse/transitive properties, disjointness, cardinality, class expressions. SHACL shapes for validation.

**Load-bearing:** configured rulesets **materialize** inferred statements, visible to ordinary queries. SHACL-enabled repositories validate data changes and can **reject a violating commit**. **SHACL must be selected when the repository is created and cannot simply be switched on later.** ([Reasoning](https://graphdb.ontotext.com/documentation/11.4/reasoning.html), [SHACL](https://graphdb.ontotext.com/documentation/11.4/shacl-validation.html))

### Property-graph vs RDF conclusion

Property-graph systems are converging on native graph schemas and database constraints; RDF systems deliberately separate semantic entailment from data-shape validation. Both traditions now accept that flexible graph storage alone is insufficient, but they preserve **different meanings of "valid."**

---

# 4. Data catalogs and governance systems

## DataHub

**Typed:** internal metadata metamodel for datasets, fields, dashboards, jobs, domains, glossary nodes, glossary terms, structured properties. Terms have hierarchy, definitions, parent groups, ownership, `Contains`/`Inherits` relationships.

**Load-bearing partly:** terms power facets, search, autocomplete, "related assets"; optional automations propagate terms along lineage; **authorization policies can target assets carrying a term or any term under a glossary group.** ([Policies](https://docs.datahub.com/docs/authorization/policies))

**Does not** validate or reject rows in the source database because a business term disagrees with them.

**Governance:** terms editable in UI or managed as files in Git and ingested via CLI. Metadata policies delegate subtrees to owners/stewards; cloud change proposals allow users to suggest terms for approval.

## OpenMetadata

**Typed:** glossary terms with parent/child hierarchy, synonyms, related terms, references, reviewers, owners, lifecycle status. Classifications contain tags, may be **mutually exclusive**.

**Enforced within the catalog:** mutual exclusion prevents conflicting labels on the same asset; classifications participate in access, retention, privacy policies; automations propagate tags, terms, owners, domains, descriptions across lineage. New terms enter **Draft** and become broadly usable only after reviewer approval. ([Glossary approval](https://docs.open-metadata.org/v1.12.x/how-to-guides/data-governance/workflows/default-workflows/glossary-approval))

## Atlan

**Typed:** glossaries, categories, terms, assets, typed semantic relations (synonym, antonym, related term, preferred term, replacement, classification, valid value).

**Load-bearing:** glossaries form access-control boundaries; categories do not. Tags on terms can propagate to linked, child, downstream assets **when enabled (disabled by default)**. Term relations are documented as contextual meaning, **not logical entailment or source-data validation.** "Atlan Bot" suggestions are inferred proposals.

## Alation

**Typed:** catalog object types, glossary terms, policies, templates, typed custom fields. **No general logical ontology of business entity classes and relationship constraints.**

**Mostly workflow guidance:** TrustCheck carries endorsements, warnings, deprecations into the Compose SQL editor. Query warnings can flag a missing filter or wrong join, **but the user may dismiss the warning and proceed.** ([Query warnings](https://docs.alation.com/en/latest/analyst/WriteQueries/QueryWarnings.html))

## Collibra

**Typed:** asset types, attribute types, relation types, complex relation types, domain types, statuses, validation rules. An asset is an instance of one asset type; **relation types specify head and tail asset types.**

**More load-bearing than most catalogs.** Asset-type assignments determine which characteristics, relations, domains, statuses, and validation rules apply. Governs Collibra metadata and lineage, **not necessarily the underlying source database.**

**Enforcement is conditional:** characteristic and relation validation can be hard **if console settings are enabled**; with validation disabled, API/import/workflow paths can add characteristics not assigned to the asset type. Scripted validation rules run only when a user explicitly selects Validate/Revalidate — **post-hoc checks, not universal write rejection.**

**Catalog pattern:** business glossaries become operational mainly when **another subsystem consumes them** — search facets, policy targeting, propagation, approval, warnings. They seldom make assertions about the validity of underlying business data.

---

# 5. Semantic layers

A separate tradition: "define the meaning once" works because the definitions **compile into every query**, not because users can browse a glossary.

## dbt Semantic Layer / MetricFlow

**Typed:** semantic models declare entities, measures, dimensions, metrics. Entities carry join semantics (primary, unique, foreign, natural).

**Load-bearing:** MetricFlow builds a semantic graph, **chooses valid join paths**, constructs a dataflow plan, generates SQL. Downstream APIs query this compiled model rather than independently rewriting metric SQL.

**Enforced before deployment:** configuration schema and semantic-graph rules validated; generated SQL checked against the data platform. Join-key classifications are **declarations used by the planner**; docs do not claim MetricFlow proves declared uniqueness against all rows.

## Cube

**Typed:** cubes contain measures, dimensions, joins, views, pre-aggregations. Joins have relationship cardinalities.

**Load-bearing:** Cube generates joins and aggregate SQL, chooses matching pre-aggregations, **exposes only modeled members through APIs**, and applies access policies before reaching the warehouse. **An incorrect cardinality declaration can still encode incorrect business meaning.**

## Looker / LookML

**Typed:** models, Explores, views, dimensions, dimension groups, measures, joins, primary keys, join relationships (one-to-one, many-to-one, one-to-many, many-to-many).

**Load-bearing:** Looker generates SQL from LookML. **Join relationship declarations change how measures are aggregated**; symmetric aggregates use primary keys and cardinality to prevent fanout errors. The LookML Validator checks syntax/references; the Content Validator identifies dashboards broken by model changes; both run in CI.

**Declared cardinality is trusted rather than continuously proven from warehouse rows; a wrong declaration generates a valid but wrong aggregate.**

## Malloy

**Typed:** sources contain fields, dimensions, measures, primary keys, joins, reusable views. Both a semantic modeling language and a query language. Model syntax and query compilation enforced; semantic definitions manually authored, **not inferred by an LLM.**

## What worked in semantic layers, and why

**Airbnb's Minerva** supplies unusually clear production evidence. Metric and dimension definitions were version-controlled, required ownership/lineage/descriptions, and underwent **code review**. A single API served the same definitions to Superset, Tableau, experimentation, Python, R, anomaly detection. **The effective feature was not a shared glossary page; it was forcing consumers through an executable interface.** ([Minerva computation](https://medium.com/airbnb-engineering/how-airbnb-standardized-metric-computation-at-scale-9afe6695b486), [Minerva API](https://medium.com/airbnb-engineering/how-airbnb-enables-consistent-data-consumption-at-scale-1c0b6a8b9206))

This is the strongest independent tradition supporting "define once": **semantics work when they compile into or mediate the query every time.**

---

# 6. AI memory and agent-context products

## Zep / Graphiti

**Typed:** Graphiti can type **both** entity nodes and fact edges through user-supplied Pydantic models. **`edge_type_map` declares which relationship types apply to source/target entity-type pairs.** Episodes are nodes connected to extracted entities by `MENTIONS`. ([Custom types](https://help.getzep.com/graphiti/core-concepts/custom-entity-and-edge-types))

**Load-bearing at extraction and retrieval:** type models guide LLM extraction and add custom properties; search can include or exclude specific node labels, edge types, properties, time ranges. Context-building examples issue **separate typed searches** for restaurants, visits, dietary preferences.

**Enforcement:** type selection and property extraction are **LLM-inferred** into structured models. The ontology is deliberately **open**: if an entity-pair lacks a mapping, Graphiti retains the relationship as generic **`RELATES_TO` rather than rejecting it.** Search filtering is deterministic after ingestion.

Zep reports improved memory benchmarks for the overall temporal-graph architecture, but this is a **vendor-authored paper** and does not isolate the contribution of entity typing from temporal validity, reranking, or other components. ([Zep paper](https://arxiv.org/abs/2501.13956))

## Mem0

**Typed:** automatically extracts people, places, organizations, concepts. **No custom node/edge ontology or relationship-type schema** in public v3 docs.

**Load-bearing for ranking:** query entities matched to graph entities; connected memories receive a boost combined with semantic and BM25 scores. Entirely **inferred**. Graph Memory has been **removed from the current open-source SDK** and is now a managed Platform feature — relevant for self-hosting comparisons. ([OSS migration](https://docs.mem0.ai/migration/oss-v2-to-v3))

## Letta / MemGPT

**No documented entity-relationship ontology.** Memory blocks have labels, descriptions, values, limits; archival passages have text, embeddings, timestamps, optional tags. Block character limits and read-only flags enforced; labels/descriptions and tags advisory.

## Cognee

**Cognee usefully separates two things that many products conflate.**

**Typed:** (a) a custom graph model is a Pydantic `DataPoint` schema defining node types, fields, nested relationships; (b) separately, an optional RDF/OWL ontology supplies classes, individuals, IRIs, parent classes, object-property links for grounding.

**Load-bearing:**
- The custom graph model is the **LLM structured-output schema** and controls which entity shapes and relationships can be emitted — **hard structured-output validation.**
- **Ontology grounding is explicitly soft:** unmatched nodes remain stored and searchable with `ontology_valid=False`; **domain/range is not enforced; no OWL entailment is performed.**
- The two modes **do not automatically stack** in one extraction pass.
- Ontologies are parsed once at resolver initialization and are **not hot-reloaded.** ([Ontologies](https://docs.cognee.ai/core-concepts/further-concepts/ontologies))

**Cognee is one of the clearest public demonstrations that "extraction schema" and "reference ontology" are distinct mechanisms with different enforcement semantics.**

---

# 7. LLM framework property graphs

## LlamaIndex `PropertyGraphIndex`

**Typed:** `SchemaLLMPathExtractor` accepts possible entity types, possible relationship types, optional entity/relation properties, and a graph validation schema.

**Load-bearing:** at ingest, **`strict=True` removes values outside the supplied schema**; `strict=False` treats the schema as a suggestion. At query time the resulting types can be used by ordinary retrieval, dynamic text-to-Cypher, or a safer Cypher template with typed parameters. A structured backend such as Kùzu can additionally enforce its own relationship schema.

**Practitioner reports — two concrete failure modes from the issue tracker:**
- Generated JSON schemas containing `additionalProperties: true` conflicted with OpenAI structured outputs and Gemini; an opt-in cleanup option was added. ([PR #20768](https://github.com/run-llama/llama_index/pull/20768))
- Property extraction has produced provider/version-specific empty or invalid results, and **strict schemas do not remove LlamaIndex's internal provenance nodes** (`Chunk` / `MENTIONS`). ([Issue #21142](https://github.com/run-llama/llama_index/issues/21142), [Issue #17549](https://github.com/run-llama/llama_index/issues/17549))

**The lesson documented by the software itself: schema-guided LLM extraction still requires deterministic post-processing, provider compatibility testing, and provenance conventions.**

## LangChain `LLMGraphTransformer`

**Typed:** `allowed_nodes` whitelists node types. **`allowed_relationships` can be a list of relation names or directional triples `(source node type, relationship type, target node type)`.** Node and relationship property whitelists supported.

**Load-bearing:** constrains graph construction, **not the later query engine.**

**Enforcement:** the model first extracts candidates. With `strict_mode=True`, LangChain applies **post-processing filters** to remove nodes and relationships outside the allowed schema; it **does not make the LLM obey perfectly** and does not create backend constraints. Tomaz Bratanic's implementation account explicitly describes strict mode as post-processing added **because prompt adherence is imperfect.** ([Implementation article](https://medium.com/data-science/building-knowledge-graphs-with-llm-graph-transformer-a91045c49b59))

**Reported bug:** correctly extracted relationship JSON was later **discarded because parser field names did not match** — "strict schema" can mean post-extraction filtering and parsing rather than guaranteed correct extraction. ([Issue #27100](https://github.com/langchain-ai/langchain/issues/27100))

---

# 8. Large in-house knowledge graphs

## Google Knowledge Graph / Freebase

**Typed:** Freebase topics could have multiple types grouped into domains with properties; compound value types represented multi-field relationships. The public KG Search API returns schema.org-compatible JSON-LD entities with multiple types.

**Load-bearing:** the public API can **restrict results by schema.org type**, so node typing directly changes query results. Internal ranking details are not public.

**Governance:** Freebase was collaboratively created and maintained by users; Google later transferred public content to Wikidata. **Current Google KG schema governance is private.**

**Knowledge Vault** describes a separate probabilistic extraction system fusing web text, tables, page structure, annotations, and prior knowledge into **calibrated fact probabilities** — evidence for automated fact population, not for automatic schema governance. ([Knowledge Vault](https://research.google/pubs/knowledge-vault-a-web-scale-approach-to-probabilistic-knowledge-fusion/))

## Amazon Product Graph / AutoKnow

**Typed:** products receive one or more product types and attribute/value pairs. The ontology suite includes a product-type taxonomy with hypernym links and **a relation-discovery model deciding which attributes apply to which product types.**

**Critically:** AutoKnow **starts from an existing, hand-engineered product taxonomy and labeled catalog**, then uses ML for taxonomy enrichment, applicable-attribute discovery, value extraction, anomaly detection, synonym discovery. Operated over **more than 11,000 product types**. Reported **87.7% product-type accuracy** and an almost **200% fact increase** — confirming both utility and residual error. ([AutoKnow](https://arxiv.org/pdf/2006.13473), [Amazon Science](https://www.amazon.science/blog/building-product-graphs-automatically))

## LinkedIn Knowledge Graph / Skills Graph

**Typed:** members, jobs, titles, skills, companies, locations, schools. Entity taxonomies include canonical identifiers, definitions, names, multilingual synonyms, relationships to other taxonomies, non-relational attributes.

**Load-bearing:** member-to-skill, job-to-skill, employment, education, and similarity relationships feed people search, recruiter search, job search, recommendations, feed, ads, analytics. LIquid's declarative graph queries use labels and relationships to generate recent and explainable recommendations.

**Governance:** combines **human taxonomists**, machine learning, external sources, crowdsourcing, and user interaction. The skills taxonomy is explicitly described as **continuously maintained by human curation plus models such as KGBert.** ([Skills taxonomy](https://www.linkedin.com/blog/engineering/data/building-maintaining-the-skills-taxonomy-that-powers-linkedins-skills-graph))

## Airbnb

**Typed:** node types with unique schemas (places, events); typed edges such as `landmark-in-city`. **Edge types carry configurable source/target constraints analogous to RDFS domain and range.** Taxonomy represented as a hierarchy of special graph nodes.

**Load-bearing:** the graph query API traverses a sequence of edge types and data filters. Airbnb indexes inventory by graph identifiers and uses taxonomy ancestors/descendants for Explore navigation, search, autocomplete, filters. ([Airbnb KG](https://medium.com/airbnb-engineering/contextualizing-airbnb-by-building-knowledge-graph-b7077e268d5a))

**Governance:** a universal taxonomy that began with Experiences and expanded across Homes, Restaurants, places, events. T-LEAF describes iterative work by taxonomists, ML systems, and product teams, evaluating coverage, usefulness, agreement. The 2019 account **does not explicitly state rejection semantics for an invalid mutation.**

## Uber / Uber Eats

**Typed:** ontology of restaurants, cuisines, menu items, and their relationships; distinguishes entity categories such as cuisine and dish type.

**Load-bearing:** offline pipelines annotate restaurants and menu items through the graph. **Online query rewriting uses hierarchy and related entities** — expanding "Asian" to Chinese and Japanese, or "udon" to related Japanese noodle terms — to alter retrieved results. ([Query understanding](https://www.uber.com/us/en/blog/uber-eats-query-understanding/))

**Enforcement:** conformance performed by ingestion pipelines and classifiers. **Public material does not establish database-level write rejection.**

---

# Convergent patterns

## 1. An ontology earns its cost only when software consumes it

Palantir's object/link/action types determine queries and writes; TigerGraph and TerminusDB validate graph storage; Stardog and GraphDB change query answers through reasoning; semantic layers compile definitions into SQL; Glean and Graphiti use types as filters and ranking/context signals. **Independent systems repeatedly make semantics executable rather than merely visible.**

## 2. Systems that care about relationship meaning type BOTH endpoints and predicates

Palantir interface links, TigerGraph edge DDL, Airbnb edge constraints, Graphiti's `edge_type_map`, LangChain's source/relation/target tuples, and OWL object properties all encode more than a relationship name.

**A fixed edge vocabulary without node types cannot express whether `imports` means package→package, file→module, symbol→module, or arbitrary concept→arbitrary concept.**

## 3. Inference and enforcement are different products

OWL/RDFS infer facts; SHACL validates graphs. LlamaIndex and LangChain let an LLM propose triples and then filter them. Cognee explicitly separates a hard Pydantic graph shape from soft ontology grounding. **Conflating these stages makes guarantees impossible to state.**

## 4. Human experts define the canonical core; automation proposes or populates

LinkedIn combines taxonomists and ML; Amazon grows a hand-engineered taxonomy with automated enrichment; Airbnb combines taxonomists, models, evaluation; Palantir permissions schema authors and reviews operational changes; catalog products route glossary proposals to stewards.

**No major published production account relies on an unconstrained small LLM as the sole maintainer of the canonical type system.**

## 5. Successful systems treat drift as a software-lifecycle problem

Palantir has branches, history, usage impact, interface versions, data migrations. TigerGraph invalidates compiled jobs after incompatible schema changes. TerminusDB versions schema and data together. Looker validates model and downstream dashboard references in Git/CI. Airbnb Minerva required review of versioned metric definitions.

## 6. Open-world escape hatches are common

Neo4j's schema is open outside the constrained portion. Graphiti falls back to `RELATES_TO`. Cognee keeps unmatched nodes. RDF permits partial schema. **This preserves recall and incremental adoption at the cost of weaker guarantees.**

## 7. Retrieval quality still needs lexical, vector, metadata, and behavioral signals

Glean combines graph structure with semantic and classical retrieval. Elastic advocates hybrid search, filters, query rules. Mem0 fuses entity, vector, BM25, temporal signals. **Ontology is one relevance signal or query constraint, not a replacement for retrieval engineering.**

## 8. The semantic-layer tradition succeeds by centralizing execution, not vocabulary

dbt, Cube, Looker, Malloy, and Minerva all make definitions pass through a compiler or serving API. **Catalog glossaries generally stop at metadata unless an automation or policy consumes them.**

---

# Where they disagree

**Hard rejection vs graceful retention.** TigerGraph, TerminusDB, Neo4j constraints, Palantir actions, and SHACL guard mode can reject invalid operations. Graphiti and Cognee preserve unknown facts through a generic relationship or ungrounded node. The first buys stronger invariants; the second buys recall, incremental adoption, and resilience to incomplete vocabularies.

**Authored vs inferred schema.** Palantir, semantic layers, TigerGraph, and RDF ontologies are primarily authored. Mem0 and Glean primarily infer. Neo4j GraphRAG can infer a guiding schema once from source text. Amazon and LinkedIn use hybrids. Authored buys stability and interpretability; inferred buys lower onboarding cost and wider coverage but requires confidence, cleanup, or fallback.

**Reasoning vs traversal.** Stardog and GraphDB infer unstored results from axioms. Neo4j, TigerGraph, Airbnb, LlamaIndex, LangChain principally use explicit labeled paths. Reasoning buys reusable logical consequences and interoperability; traversal buys simpler operational semantics and easier performance control.

**Query-time reasoning vs materialization.** Stardog reasons lazily at query time. GraphDB materializes inference closure during load/commit — higher write cost, faster reads.

**Data ontology vs operational ontology.** Palantir includes actions, functions, security, writeback inside its ontology. Most graph databases model data and leave actions to applications.

**Universal ontology vs domain-local models.** Palantir promotes a shared organization-wide model; Cube, dbt, Graphiti, and most catalogs permit local domain models and scoped governance.

**Semantic vs structural correctness.** A database can enforce that `works_at` connects `Person` to `Company` and still be wrong about whether Alice works there. Conversely a free-form extracted fact may be true but outside the schema. **No reviewed system demonstrates that an ontology by itself establishes factual truth.**

---

# Closest analogues to openCG

## 1. LlamaIndex `PropertyGraphIndex`

The closest direct pipeline analogue: unstructured documents chunked, LLM extracts typed entities and relations, developer supplies allowed node/edge types and valid patterns, strict mode removes out-of-schema output, graph retrieval combined with source chunks and vector retrieval. Its provenance `Chunk`/`MENTIONS` convention and provider-specific structured-output issues are directly relevant at open-source RAG scale.

## 2. LangChain `LLMGraphTransformer`

The closest API-level analogue to adding node types and source/relation/target restrictions around an existing LLM extraction stage. Demonstrates a lightweight model: developer-authored whitelists, LLM structured output, deterministic post-filtering, **no requirement for OWL or a dedicated ontology service.** Also demonstrates the limit: no schema lifecycle, no database constraints, no correctness guarantees.

## 3. Cognee

The closest conceptual analogue for separating two candidate meanings of "ontology" at small, self-hostable scale: a **hard Pydantic extraction model** controlling nodes/fields/relationships, and a **soft RDF/OWL reference vocabulary** used for canonical names, aliases, IRIs, inherited context while retaining unmatched entities. Its documentation explicitly states these mechanisms differ, do not automatically stack, and provide different guarantees.

**Palantir is the most prominent commercial reference but not the closest scale or product analogue:** its "ontology" includes an operational application backend, transactional actions, security, function execution, SDK generation, and external-system writeback.

---

# Bottom line: what ontology actually does in shipping systems

Across the systems reviewed, "ontology" performs one or more of six concrete jobs:

1. **Canonicalization** — stable names, aliases, identities, categories (Google/Freebase, LinkedIn, Amazon, Cognee).
2. **Extraction control** — allowed node types, relationship types, properties, endpoint patterns (LlamaIndex, LangChain, Graphiti, Cognee).
3. **Query control** — deterministic filtering, traversal, SQL generation, aggregation behavior, ranking (Palantir, Airbnb, semantic layers, Glean, Mem0).
4. **Inference** — deriving unstored types or relationships from axioms and rules (Stardog, GraphDB).
5. **Validation** — reporting or rejecting structurally invalid graph data (SHACL systems, TigerGraph, TerminusDB, Neo4j constraints).
6. **Governed action** — deciding who may mutate operational state and under what conditions (principally Palantir).

**A vocabulary that performs none of these jobs is descriptive documentation. A vocabulary that changes model output but is not followed by deterministic validation is a prompt. A schema that changes retrieval, query compilation, inference, validation, or authorization is load-bearing.**
