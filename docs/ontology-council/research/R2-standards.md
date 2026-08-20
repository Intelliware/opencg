# R2 — Standards & Formalisms Dossier

**Model:** Opus 5 thinking @ max
**Scope:** what the formal tradition knows, what it costs, what to borrow, what to avoid. No design recommendations.

---

## 0. Executive verdict on the crux question

**Is `domain`/`range` the right primitive, or a false friend?**

**It is a false friend at the level of semantics and terminology, and a real requirement at the level of intent.** Both halves matter.

The false-friend half is not interpretation. In RDFS and OWL, `rdfs:domain` and `rdfs:range` are **inference rules**, not constraints:

| | If S contains | then S RDFS entails |
|---|---|---|
| rdfs2 | `aaa rdfs:domain xxx . yyy aaa zzz .` | `yyy rdf:type xxx .` |
| rdfs3 | `aaa rdfs:range xxx . yyy aaa zzz .` | `zzz rdf:type xxx .` |

— [RDF 1.1 Semantics §9.2.1](https://www.w3.org/TR/rdf11-mt/#patterns-of-rdfs-entailment)

**Read rdfs2 against openCG's situation.** If you assert `calls rdfs:domain Function` and then extract `README.md --calls--> parse()`, RDFS does not reject the edge. **It concludes that `README.md` is a Function.** The bad data is not caught; it is laundered into a new assertion.

The OWL 2 Primer names this exact failure and calls it an error:

> "assume that we also specify the information that Felix is in the class `Cat` and that Felix `hasAge` 9. From the combined information, it would then be possible to deduce that Felix is also in the class `Person`, which is probably not intended. **This is a commonly modeling error: note that a domain (or range) statement is not a constraint on the knowledge, but allows a reasoner to infer further knowledge.**"

— [OWL 2 Primer §4.8](https://www.w3.org/TR/owl2-primer/#Datatypes)

**The real-requirement half:** what openCG wants — an edge of type `calls` should connect a function-like thing to a function-like thing, violations surfaced — is legitimate, well-specified, thoroughly standardised. **It just is not called `domain`/`range` anywhere that it means validation.** Its actual names:

- RDF-land: a **SHACL node shape** targeted with `sh:targetSubjectsOf` / `sh:targetObjectsOf`, constrained with `sh:class`.
- Property-graph-land: an **edge type with endpoint node types** — PG-Schema requirement **R2**: "Schemas must allow defining types for edges that specify their labels and properties as well as the types of incident nodes."

**A third fact the council needs.** openCG's stated model is "edges are typed; nodes are not." **In every formalism surveyed here, an endpoint constraint is a statement about node types.** `rdfs:domain` takes a class; `sh:class` takes a class; PG-Schema edge types name node types. There is no formalism in which edge endpoints can be constrained without a notion of node type. **Adopting this primitive therefore presupposes typing nodes.** That is a factual property of the formalisms, not a recommendation.

**Empirical weight.** The Manchester group ran "more than a dozen workshops, tutorials and modules" teaching OWL-DL:

> "In most languages domain and range constraints on properties are simply checked and generate errors if violated. In OWL they are axioms and are used in reasoning, with potentially far-reaching and unexpected effects. […] **After problems with open world reasoning, difficulties with domain and range constraints are the largest single source of errors and difficulty in our experience with new users of OWL.**"

— Rector et al., [*OWL Pizzas*](http://www.cs.man.ac.uk/~rector/papers/common_errors_ekaw_2004.pdf), EKAW 2004, §4.2

The same paper names the debugging cost: when a coercion fires, "the reason for the classifier's action is **nowhere to be seen** in the definition of `Choc-icecream`, `Icecream` or `Pizza`. It must be searched for in the domain restriction on `hasTopping`."

---

## 1. Terminology discipline

**Class.** A set-like grouping of individuals. RDF distinguishes a class from its extension: "Two classes may have the same set of instances but be different classes." ([RDFS §2](https://www.w3.org/TR/rdf-schema/#ch_classes))

**Instance / individual.** A member of a class. OWL calls them *individuals*.

**Type.** Overloaded, and the overload is dangerous. In RDF, `rdf:type` just asserts class membership. In the property-graph tradition, PG-Schema draws the line sharply:

> "**Type** is a property assigned to elements […] **Constraint** is a closed formula over a vocabulary that permits quantification over elements of the same type. […] **types are of local nature while constraints are more global.** […] Consequently, types are typically verified statically whereas constraints are dynamically verified."

**That local/global split is the most useful distinction in this dossier for a systems team, because it predicts where the check can run.** Endpoint checking on an edge is local (touch the edge and its two nodes). "Every `Module` must have at least one `defined_in` edge" is global.

**Entity.** Not a formalism term. A node is a syntactic token; an entity is what it refers to. Two nodes may denote one entity.

**Concept.** In SKOS this is precise and it is **not** a class. `skos:Concept` is itself an `owl:Class`, so its members — the concepts — are *individuals*:

> "SKOS concepts are OWL individuals; […] The restrictions on OWL-DL prevent treating SKOS concepts as OWL classes."

— [SKOS Primer §5.2](https://www.w3.org/TR/skos-primer/#secskosowl)

**openCG already calls its nodes "concepts," which is compatible with the SKOS reading and incompatible with the OWL-class reading. Worth settling out loud.**

**Shape.** A validation object, not a semantic one. A shape says nothing about what is *true*; only about what is *acceptable*.

**Ontology.** In OWL, an ontology is a set of axioms plus a header — a *theory*, evaluated for consistency and entailment. **It is not a schema.** The Primer says so twice:

> "OWL 2 is not a schema language for syntax conformance. […] **This should be kept in mind as OWL has some features that a user might misinterpret this way.**"
> "OWL 2 is not a database framework. […] database schemata often come with the prescriptive constraint semantics mentioned above."

— [OWL 2 Primer §2](https://www.w3.org/TR/owl2-primer/#What_is_OWL_2)

**Schema.** Hogan et al. distinguish three kinds for graphs: a **semantic schema** (ontology axioms, open-world, entailment), a **validating schema** (shapes, closed-world, conformance), and an **emergent schema** (a summary derived from data).

**Recommended discipline:** when someone says "schema," ask *semantic, validating, or emergent*. When someone says "type," ask *node or edge, and is the check local*. When someone says "concept," ask *SKOS concept (an individual) or OWL class (a set)*.

---

## 2. RDFS and OWL: what domain and range actually mean

### 2.1 The normative statement

> "`rdfs:domain` […] is used to **state** that any resource that has a given property **is an instance of** one or more classes."

Note the verb: *states that*, not *requires that*.

### 2.2 The trap most people miss: multiple domains CONJOIN

> "Where a property P has more than one `rdfs:domain` property, then the resources denoted by subjects of triples with predicate P are instances of **all** the classes stated."

— [RDFS §3.2](https://www.w3.org/TR/rdf-schema/#ch_domain)

**This is the intersection, not the union.** Anyone reaching for domain/range as a validation vocabulary will naturally want *disjunction* — "`calls` may originate from a Function **or** a Method" — and will write two domain statements to get it. In RDFS this means "the subject is both a Function and a Method simultaneously," **which will silently produce nonsense rather than an error.**

### 2.3 RDFS explicitly declines to say what applications should do

> "RDF Schema provides a mechanism for describing this information, but does not say whether or how an application should use it. […] **data checking tools might use this to help discover errors in some data set**, an interactive editor might suggest appropriate values, and a reasoning application might use it to infer additional information."

— [RDFS §4](https://www.w3.org/TR/rdf-schema/#ch_domainrange)

**Weigh this honestly:** it is **non-normative**, about what an *application* may choose to do, and does not change the formal semantics. A tool that reads domain/range and reports violations is doing something the spec permits and the semantics does not sanction. **That is a coherent position, but it means the tool is not implementing RDFS; it is implementing a private convention that reuses RDFS's vocabulary.**

### 2.4 When does a domain violation become an error?

Almost never in RDFS, and only conditionally in OWL.

**RDFS: only via datatype value-space clashes.** Unsatisfiability arises *because the value spaces of two datatypes are disjoint*. For ordinary user-declared classes, no disjointness is assumed, so you get silent coercion instead.

**OWL: only if you also assert disjointness.** "If `Pizza` and `Icecream` are not disjoint, then `Choc-icecream` will be classified as a kind of `Pizza`. If, on the other hand, `Icecream` is disjoint from `Pizza`, then `Choc-icecream` will be unsatisfiable."

And OWL classes are **not** disjoint by default: "in OWL, classes are overlapping until disjointness axioms are entered. […] **One of the most common errors in building ontologies in OWL has been to omit the disjointness axioms.**"

**The full recipe** for validation-like behaviour from OWL domain/range: assert the domain, assert pairwise disjointness of every sibling class, run a DL reasoner, interpret "unsatisfiable class" as "constraint violated." That yields a boolean inconsistency for the whole ontology with **no per-edge localisation, no severity, and no report format.**

### 2.5 RDFS has no local scope

> "The basic facilities provided by `rdfs:domain` and `rdfs:range` do not provide any direct way to indicate property restrictions that are local to a class."

Domain/range are **global** statements about a property everywhere it is used.

---

## 3. The OWL 2 profiles

> "**Note that none of the profiles is a subset of another.**"

That clause is a practical trap: you cannot pick one and later "upgrade" along a chain.

**Baseline:** full OWL 2 under RDF-Based Semantics is **undecidable** for every reasoning problem. Under Direct Semantics it is **N2EXPTIME-complete**; conjunctive query answering is *decidability open*.

| Profile | Design goal | Complexity | Good for |
|---|---|---|---|
| **EL** | Very large numbers of classes/properties | All main tasks **PTIME-complete** | Big terminologies (SNOMED CT) |
| **QL** | Very large instance volumes, query answering | Consistency/subsumption **NLogSpace-complete**; data complexity **in AC⁰** | Ontology-mediated query answering over a relational DB via rewriting |
| **RL** | Scalable reasoning without giving up too much | All main tasks **PTIME-complete** | Rule-engine implementations |

**QL is the profile most relevant here.** It was designed around conceptual modelling and relational implementation:

> "designed so that data (assertions) that is stored in a standard relational database system can be queried through an ontology via a simple rewriting mechanism, i.e., by rewriting the query into an SQL query […] **without any changes to the data**."

**The relevant fact for a Postgres-backed system:** the class of things QL can express — class hierarchies, domain/range, disjointness, inverses — is precisely the class of things that compile to SQL. **If the council ever wants entailment (not validation) over a class hierarchy, QL is the honest ceiling, and its implementation strategy is "rewrite to SQL," not "install a triple store."**

**What none of the profiles buys you: validation.** All three are still open-world inference systems.

---

## 4. SHACL and ShEx: the validation answer

### 4.1 SHACL, precisely

- A **shape** targets nodes and declares constraints. **Node shapes** apply to focus nodes; **property shapes** (any shape with `sh:path`) apply to nodes reachable along a path.
- **Targets:** `sh:targetNode`, `sh:targetClass`, `sh:targetSubjectsOf`, `sh:targetObjectsOf`.
- **Constraint components:** `sh:class`, `sh:datatype`, `sh:nodeKind`, `sh:minCount`, `sh:maxCount`, `sh:pattern`, `sh:in`, `sh:closed`, `sh:node`, `sh:not`/`sh:and`/`sh:or`/`sh:xone`, `sh:qualifiedMinCount`/`sh:qualifiedMaxCount`, `sh:equals`/`sh:disjoint`/`sh:lessThan`.

**`sh:targetSubjectsOf` and `sh:targetObjectsOf` are the exact validation counterparts of domain and range:**

> "If `s` has value `p` for `sh:targetSubjectsOf` […] the set of nodes in a data graph `DG` that are **subjects** of triples in `DG` with predicate `p` is a target."
> "[…] `sh:targetObjectsOf` […] the set of nodes […] that are **objects** of triples […] is a target."

— [SHACL §2.1.3.4–2.1.3.5](https://www.w3.org/TR/shacl/#targetSubjectsOf)

The canonical shape:

```turtle
ex:NodeKindExampleShape
	a sh:NodeShape ;
	sh:targetObjectsOf ex:knows ;
	sh:nodeKind sh:IRI .
```

Swap `sh:nodeKind sh:IRI` for `sh:class ex:Function` and you have "the range of `calls` is `Function`, **checked**." Same intent as `rdfs:range`, opposite semantics, same locality: **it touches one edge and one endpoint.**

### 4.2 SHACL severity — read carefully, it is commonly misread

Three severities: `sh:Info`, `sh:Warning`, `sh:Violation` (default).

**But:**

> "**The specific values of `sh:severity` have no impact on the validation**, but MAY be used by user interface tools to categorize validation results."

> "The value of `sh:conforms` is `true` **if and only if the validation did not produce any validation results**, and `false` otherwise."

— [SHACL §2.1.4, §3.6.1.1](https://www.w3.org/TR/shacl/#conforms)

**Consequence, stated plainly: a graph with nothing but `sh:Warning`-severity results still reports `sh:conforms false`.** The spec's own worked example confirms it.

**So SHACL severity is result metadata for consumers, not a gate.** If a system wants "warnings recorded, violations block," SHACL gives you the *vocabulary and per-result labelling* to express that cleanly, and the block-or-not decision remains entirely the application's. **This is the right division of labour, but do not imagine the spec makes the decision for you.**

### 4.3 The validation report is the underrated part

Each `sh:ValidationResult` carries a fixed, machine-readable set: `sh:focusNode`, `sh:resultPath`, `sh:value`, `sh:sourceShape`, `sh:sourceConstraintComponent`, `sh:resultMessage` (language-tagged, multi-valued), `sh:resultSeverity`, `sh:detail` for nested causes.

**A well-designed, battle-tested error schema for graph constraint violations, borrowable without adopting a single line of RDF.**

Two further properties:
- **Validation is idempotent and non-mutating.** "the data graph and the shapes graph MUST remain immutable […] SHACL processing is thus idempotent."
- **Ill-formed shapes are undefined behaviour.** SHACL ships a SHACL shape for shapes graphs — *validate your validator's config.*

### 4.4 SHACL also does inference — separately, and by choice

SHACL-AF defines `sh:rule` (`sh:TripleRule`, `sh:SPARQLRule`), guarded by `sh:condition`, ordered by `sh:order`.

**The design point:** SHACL keeps validation and inference in **separate, explicitly invoked mechanisms with separate vocabulary.** RDFS fuses them into a single construct, **which is precisely why `rdfs:domain` behaves surprisingly.** This separation is the architectural lesson of SHACL, independent of RDF.

`sh:condition` means a rule fires only on focus nodes that *conform to a named shape* — "only infer from data you have already validated," declaratively.

### 4.5 SHACL vs ShEx, honestly

Both are closed-world (CWA + UNA), unlike OWL (OWA + NUNA).

| | SHACL | ShEx |
|---|---|---|
| **Standing** | W3C Recommendation (2017) | Community Group report, **not** a W3C Standard |
| **Metaphor** | Constraint language, Schematron-for-RDF | Grammar/schema language |
| **Semantics** | Core independent of SPARQL; no denotational semantics in original spec | Denotational semantics in spec |
| **Targeting** | Built-in (`sh:targetClass`, etc.) | Requires an external **ShapeMap** |
| **Closure** | `sh:closed` + `sh:ignoredProperties` | `CLOSED` + `EXTRA` |

**The most cited honest criticism of SHACL:**

> "it can be difficult for users to distinguish the case in which a node is valid because it was checked against some shape, versus the case in which a node is **not valid but was ignored** by the SHACL processor because it was not reached during the validation process."

— [Labra Gayo et al., *Validating RDF Data*](http://book.validatingrdf.com/bookHtml013.html)

**A real operational hazard: `sh:conforms true` can mean "everything checked out" or "nothing got checked." Any borrowed design needs to report *coverage* alongside conformance.**

**Verdict:** SHACL has standards standing, tooling, a designed error format, severity levels. ShEx has cleaner formal semantics. For a small team borrowing *ideas*, SHACL's vocabulary and report structure are the more valuable artefact.

---

## 5. SKOS: why `broader` is deliberately not `subClassOf`

### 5.1 The formal model

From SKOS Reference §8: `broaderTransitive` and `narrowerTransitive` are `owl:TransitiveProperty`. **`broader` and `narrower` are not.** `skos:related` is symmetric and **disjoint** with `skos:broaderTransitive`.

**The two-tier design is the cleverest thing in SKOS:**

> "By convention, `skos:broader` and `skos:narrower` are only used to assert a **direct (i.e., immediate)** hierarchical link […] to support this usage convention, the properties `skos:broader` and `skos:narrower` are **not declared as transitive**. […] By convention, the properties `skos:broaderTransitive` and `skos:narrowerTransitive` are **not used to make assertions**. Rather, these properties are used to **infer the transitive closure**."

> "This pattern allows the information about direct hierarchical links to be preserved, which is necessary for many tasks […] whilst also providing a mechanism for conveniently querying the transitive closure."

**Asserted edges and derived closure are kept in separate properties. Any system storing a hierarchy can adopt this for free.**

### 5.2 Why `broader` is not subclass — the spec's own example

> "Consider for instance a case where `ex2:vehicles` is said to be broader than `ex2:cars`, which is itself asserted to be broader than `ex2:wheels`. **It may be problematic if 'wheels' is automatically inferred to be a narrower concept with respect to 'vehicles'.** SKOS anticipates such problems by not defining `skos:broader` and `skos:narrower` as generally transitive."

— [SKOS Primer §2.3.1](https://www.w3.org/TR/skos-primer/#secmodel)

`vehicles → cars → wheels` is a genus/species link followed by a whole/part link. `rdfs:subClassOf` **is** transitive and would happily conclude every wheel is a vehicle. **SKOS refuses to.**

**Two permissions that surprise people:**
- **Cycles are legal.** "there is no condition requiring that `skos:broaderTransitive` be irreflexive." Detection recipe: compute the closure, look for `X broaderTransitive X`.
- **Poly-hierarchy is expected.** `ex:dog` under both `ex:mammals` and `ex:domesticatedAnimals` — "a pattern which arises naturally."

### 5.3 When SKOS applies vs OWL

**The discriminating question: do you want machine inference over class membership, or a navigable vocabulary of subjects?**

- "a user or retrieval algorithm should walk from a narrow topic to a broader one, preserving which links were asserted" → **concept scheme. SKOS.**
- "given X is a `Method`, conclude X is a `CodeEntity`, and detect a contradiction if X is also a `Document`" → **class hierarchy. OWL + disjointness + a reasoner.**

"We'll just treat concepts as classes too" requires OWL Full, which is **undecidable**.

---

## 6. Property-graph schema: what is genuinely available

**This section matters most for openCG because Apache AGE is a property-graph engine, not a triple store.**

### 6.1 The state of the field, per the standards authors

Twenty authors including Neo4j, TigerGraph, AWS and Google staff, seven on the ISO GQL working group:

> "Despite the maturity of commercial and open-source property graph databases, **their schema support is limited**. […] **Our inspection of eleven property graph engines reveals a fragmented landscape, where no system offers comprehensive schema support.**"
> "No existing graph database system nor currently envisioned standard covers this arsenal of features; **nor do they provide full schema validation support**."

**The honest baseline: anyone expecting to inherit endpoint-typing from the database will be disappointed.**

### 6.2 PG-Schema: the reference formalism

**Requirement R2 is exactly the primitive under discussion:**

> "**R2 Edge types.** Schemas must allow defining types for edges that specify their labels and properties as well as the types of incident nodes."

**OPEN vs CLOSED element types:** "closed types forbid any content that is not explicitly mentioned, whereas open types allow any such content. […] **By default, types are closed.**"

**STRICT vs LOOSE graph types** — the schema-maturity dial:

> "`LOOSE` allows for partial validation […] the validation process simply assigns types to as many nodes and edges in the graph as possible, but **without the restriction that every node or edge should receive at least one type**."

**Three deployment scenarios:** *schema-first* (prescriptive, limits modifications), *flexible schema* (descriptive, arrives with data), *partial schema* ("enforce a prescriptive schema over stable parts of the data and maintain a descriptive schema depicting the whole data including its evolving parts").

Syntax — note the ASCII-art edge type carrying its endpoint types:

```
CREATE NODE TYPE (personType : Person {name STRING, OPTIONAL birthday DATE})
CREATE EDGE TYPE (: personType) -[friendType : Knows & Likes {since DATE}]-> (: personType)
CREATE GRAPH TYPE fraudGraphType STRICT { ... }
```

**Inheritance in PG-Schema is multiple and structural.** "inheritance automatically conflates properties that are compatible." An incompatible combination yields a type that "would be impossible to instantiate, and as such it would be redundant." **That is the whole of PG-Schema's diamond resolution: compatible properties merge, incompatible ones make the type vacuous. No linearisation, no method-resolution order — because these are data types, not behaviour.**

### 6.3 ISO GQL

**ISO/IEC 39075:2024**, published 2024-04, 610 pages, first new ISO database query language standard since SQL. ISO life-cycle stage **90.92, "To be revised."**

> "a **fixed-schema graph can contain only the node types and edge types specified in the graph type**."

**Two caveats:** the PG-Schema authors (who include GQL editors) say schema support is "limited both in existing systems and in the first version of the GQL Standard." And the standard is **paywalled** — real friction for an open-source project.

### 6.4 Neo4j

**Classic constraint set:** property uniqueness (all editions); property existence, property type, key constraints (**Enterprise Edition**).

**Notice what is absent: any constraint on what a relationship may connect.** You can require a `:CALLS` relationship has an INTEGER `weight`; you **cannot** require it goes from `:Function` to `:Function`. **That absence is the single most important fact in this subsection.**

**Graph types** are Neo4j's GQL-aligned answer: "Cypher 25 only. Enterprise Edition. Introduced in Neo4j 2026.02. […] generally available starting in Neo4j 2026.06." And: "Cypher supports **open graph types** […] It does not impose any constraints on nodes, relationships, and properties not included by the graph type."

**Neo4j's label model:** "A node can have zero to many labels." "A relationship must have exactly one relationship type."

**There is no inheritance between labels.** `:Actor` is not a sub-label of `:Person`; a node that is both simply carries both. **Multi-label nodes are how the property-graph tradition gets the effect of multiple classification, and it is flat: no closure, no subsumption, no reasoner.**

### 6.5 Apache AGE — the tightest constraint in this dossier

> "A label is an identifier that classifies vertices and edges into certain categories. **Edges are required to have a label, but vertices do not.**"
> "A vertex **may be assigned a label**" — data format `{id:1; label: 'label_name'; properties: {...}}::vertex`
> "**An edge is assigned exactly one edge type.**"

— [Apache AGE manual, Data Types](https://age.apache.org/age-manual/master/intro/types.html)

**The `label` field is singular for both vertices and edges. AGE gives you at most ONE label per vertex, where Neo4j gives many.** Any scheme leaning on multi-label nodes to express multiple classification **does not port to AGE's label mechanism.** Multiple classification in AGE has to live in `properties` (agtype/JSONB) or in ordinary relational tables.

**Constraints:** AGE has **no `CREATE CONSTRAINT` DDL.** You drop to PostgreSQL indexes over the `agtype` accessor:

```sql
CREATE UNIQUE INDEX person_id_idx
  ON mygraph.person (ag_catalog.agtype_access_operator(properties, '"id"'::agtype));
```

(The naive `properties->>'key'` form fails with an operator error — [apache/age-website #204](https://github.com/apache/age-website/issues/204).)

**Summary of what AGE gives natively for an ontology layer: labels (one per element) and PostgreSQL.** Everything else — endpoint typing, class hierarchies, closure, cardinality, severity — is application or plain-SQL territory. **Not necessarily bad news: it means the design space is ordinary relational engineering with well-understood costs. But no part of the formal apparatus arrives for free.**

---

## 7. Class hierarchies: single vs multiple inheritance

### 7.1 What the tradition actually converged on

**The problem multiple inheritance causes is a maintenance problem, and it is real.** Rector's normalisation work, from ~15 years of OpenGALEN, proposes "decomposing or 'untangling' the ontology into independent disjoint taxonomies which are then recombined using definitions."

The ODP catalogue states the two failure modes crisply:

> "(i) the ontology becomes very difficult to maintain […] in a polyhierarchy the process becomes very inefficient and error-prone. (ii) the semantics are implicitly stated, not explicitly: any other ontologist or reasoner only knows that a class is a subclass of its superclasses, **without knowing why**."

**But the resolution is not "one parent." It is "one asserted parent, many inferred."**

> "It is unfortunately still lore in some parts of that ontology community that Multiple Inheritance (MI) is bad and that Single Inheritance (SI) ontologies are somehow purer or better. **This is dangerous advice**, although there is a kernel of truth here."

> "In fact, it is good ontology engineering practice to **never assert MI, only infer it**. Following the Rector normalization methodology, the 'primitive skeleton' should ideally form a tree, but the domain ontologies defined using these skeletons will be inferred polyhierarchies […] **This has no effect on the end-user who still consumes the ontology as a polyhierarchy, but has a huge benefit for the ontology maintainer.**"

— [Mungall, *Single-inheritance principle considered dangerous*](https://douroucouli.wordpress.com/2019/05/10/ontotip-single-inheritance-principle-considered-dangerous/)

**The council must not miss the price tag.** "Infer the polyhierarchy" means running a DL classifier over logical definitions. The Rector method requires disjointness axioms throughout, logical definitions rather than asserted parents, bridging axioms in separate modules, **and a reasoner in the loop.** That is a full OWL toolchain plus an ontologist.

**The circumstances in which single inheritance is *most* damaging:**

> "(1) the ontology is SI (2) the ontology has many compositional classes (3) there are no logical definitions / Rector normalization, hence **no hope of inferring the complete classification** (4) The ontology is widely used."

**Conditions (1), (3) and (4) are plausible for openCG, and (2) is the discriminator: the risk of single inheritance scales with how compositional the class vocabulary is.** A dozen coarse classes with orthogonal-free meanings is a different animal from 70,000 compositional ones.

### 7.2 What diamond resolution costs, by domain

- **Behaviour-bearing systems (OO languages):** a diamond requires linearisation — a total order over ancestors — because a method call must resolve to one implementation. **That is where the genuine complexity lives.**
- **Data-typing systems:** no method to dispatch, so the diamond is a *property-compatibility* question. PG-Schema's answer is the whole answer. **No linearisation needed.**
- **Logical systems:** no diamond problem in the OO sense. What *does* get expensive is disjointness checking — finding out *why* a class became unsatisfiable requires a reasoner and explanation tooling.

### 7.3 Where multiple inheritance is genuinely needed

**Wherever classification is along orthogonal dimensions.** Rector's normalisation exists precisely because domains factor into independent axes — "anatomy, substance, function, role" — and real things are classified on several at once. SKOS records the same shape as normal in topical vocabularies.

### 7.4 Is "one parent" defensible?

**In favour.** Single asserted parenthood is the target state of the most respected methodology in the field. Trees admit the cheap encodings in §8. Trees make cycle-freedom trivially checkable. The maintenance pathologies documented for *asserted* polyhierarchies are real and sourced.

**Against.** The people closest to the practice call the bare principle "dangerous advice." PG-Schema — the most recent, most consensus-driven property-graph schema formalism — chose **multi-inheritance** as a headline feature. Neo4j (many labels) and SKOS permit multiple classification by default. **And there is an asymmetry in migration cost:** going from single to multiple later invalidates the cheap subsumption encodings (§8.2) and every query written against them; going from multiple to single is a data-modelling exercise.

**The honest summary: "one parent" is defensible as a *discipline on what humans assert*. It reliably gets regretted when it is a *hard limit on what the data model can represent*, particularly if the class vocabulary turns out to be compositional.**

---

## 8. Subsumption computation

### 8.1 The four families

**(1) Recursive traversal at query time.** PostgreSQL `WITH RECURSIVE`. Cost paid per query. Write cost zero. **Two non-negotiable operational requirements: index the join column, and guard the depth** — a recursive CTE with a cycle in the data does not terminate.

**(2) Materialised transitive closure (closure table).** Store `(ancestor, descendant, depth)` for every reachable pair. Reads become an indexed lookup. Storage is the killer in dense hierarchies — "O(n·log n) to O(n²) in dense trees." Compensating: "Inserts and moves only touch paths related to the changed branch" and "Excellent concurrency characteristics."

**The framing worth adopting: the closure table is the read surface; the recursive walk is the body of the refresh job that maintains it.**

**(3) Interval / nested-set encoding.** The classic result, whose original motivation was *exactly* subclass hierarchies:

> "We present a transitive closure compression technique, based on labeling spanning trees with numeric intervals, and provide both analytical and empirical evidence of its efficacy, **including a proof of optimality**."
> "[…] the management and use of **subclass (IS-A) hierarchies in knowledge representation systems**."

— Agrawal, Borgida & Jagadish, SIGMOD 1989

**The hard limitation:**

> "Assume we have found a tree cover (a spanning tree) of the given DAG G […] Then, for any vertex, we only need to remember those nodes that it can reach, but the reachability is not embodied by the interval labels. […] The proposed algorithm finds the best tree cover that can maximally compress the transitive closure. **The cost of such a procedure, however, is equivalent to computing the transitive closure.**"

— Jin et al., SIGMOD 2008

**This is the single most decision-relevant fact in §7 and §8 combined.** The one-interval-per-node encoding is a *tree* encoding. The moment the hierarchy becomes a DAG — the moment you permit two parents — a node needs a *set* of intervals plus a residual edge list, and computing the optimal cover costs as much as computing the closure you were avoiding. **The cheapest subsumption encoding and multiple inheritance are mutually exclusive.**

**(4) Materialised path (`ltree`).** PostgreSQL ships this as a first-class **trusted** extension:
- Stores `Top.Science.Astronomy.Astrophysics`.
- Operators: `@>` ancestor, `<@` descendant, `lquery` patterns, `ltxtquery`.
- Functions: `nlevel`, `subpath`, `index`, `lca`.
- Indexes: B-tree, hash, **GiST** (`gist_ltree_ops`).
- Limits: label ≤1000 chars; path ≤65535 labels.
- The GiST opclass "approximates a set of path labels as a bitmap signature" with tunable `siglen`; the `ltree[]` variant is explicitly **lossy**.

**`ltree` is genuinely well suited to a single-parent taxonomy in Postgres: zero new infrastructure, a native index, a readable stored form that doubles as a human-legible breadcrumb. Its limitation is the same as nested sets: a path encodes one parent.**

### 8.2 Decision table

| Approach | Ancestry check | Descendant set | Insert leaf | Move subtree | Handles DAG? | Extra storage |
|---|---|---|---|---|---|---|
| Recursive CTE | O(depth) per query | O(subtree) per query | O(1) | O(1) | Yes (needs cycle guard) | none |
| Closure table | indexed lookup | indexed lookup | O(depth) | O(subtree × depth) | Yes | O(n·log n) → O(n²) |
| Interval / nested set | integer comparison | range scan | renumbering | heavy renumbering | **No** | O(n) for trees |
| `ltree` path | prefix test, GiST | prefix scan | O(1) | rewrite whole branch | **No** | O(n·depth) |

**The size question.** The formal literature gives no universal breakpoint; the breakpoint is governed by *query rate × depth*, not node count. But a clean qualitative threshold is well supported: **a hierarchy of a few hundred classes queried at ordinary web rates does not need any encoding at all.** Agrawal et al.'s motivation was a closure growing "from O(n) to O(n²)" — biting in the tens of thousands of nodes, not the hundreds. The reachability-index literature targets graphs of millions of vertices. **A class taxonomy for a code-and-docs knowledge graph is several orders of magnitude below where any of this machinery earns its complexity.**

---

## 9. Schema evolution

### 9.1 The empirical picture

> "in the last five years the number of concepts in GO and NCI Thesaurus **more than doubled** (from 13,163 to 28,250 and from 28,740 to 68,862). While most changes are additions, many concepts have been deleted or declared obsolete (**about 25 and 50 per month in GO and NCI Thesaurus, respectively**). […] **In particular, annotations referring to deleted or obsolete concepts are no longer valid and may have to be deleted or adapted.**"

— Hartung et al., BMC Bioinformatics 2009

**That last sentence is the whole problem in one line: the ontology changes, and the annotations pointing into it go stale.** For openCG, "annotations" are extracted graph edges and node classifications.

The reuse-fragility picture also poses the question nobody has settled: "Does the local ontology subscribe to the definition of the terms at the time of publishing, every time the local ontology changes or for every evolution of the reused term?" **That question has an exact analogue for openCG: does an extracted edge conform to the class vocabulary as of extraction time, or as of now?**

### 9.2 What the standards give you

**OWL 2 versioning:** ontology IRI + optional **version IRI**. Plus annotation properties: `owl:versionInfo`, `owl:priorVersion`, `owl:backwardCompatibleWith`, `owl:incompatibleWith`, `owl:deprecated`.

**Critically, `owl:deprecated` is an annotation property. It carries no logical force; a reasoner ignores it. Deprecation is a *social* mechanism with a standardised spelling — which is exactly why it works. It never breaks anything.**

**OBO Foundry Principle 19: Stability of Term Meaning** — the most operationally precise deprecation protocol available, **formally adopted only in 2025**, encoding two decades of hard-won lessons.

> "changes to the definition of a term should never substantially shift its meaning. […] **its set of referents MUST remain stable**."
> "**If a proposed change to the definition would substantially change its referents, then a new term with new IRI and definition MUST instead be created.**"

**Obsoletion protocol:**
1. Mark obsolete — `owl:deprecated "true"^^xsd:boolean` / `is_obsolete: true`
2. Indicate any exact replacement — `term replaced by` (IAO:0100001) / `replaced_by:`
3. Prepend the exact string `"obsolete "` to the label
4. Optionally prepend `"OBSOLETE. "` to the definition — consistently if at all

**And the automated checks, the interesting part:**

> "An ERROR if any obsolete term does not also have 'obsolete ' prepended to the label"
> "An ERROR if any obsolete term (as indicated by label or definition) lacks an `owl:deprecated` property"
> "**An ERROR if an obsolete term has, itself, any logical axioms (including any subClassOf/is_a declarations) or if it is referenced by logical axioms from other terms**"

**That third ERROR is load-bearing: a deprecated term must be logically inert and unreferenced.** It survives as an identifier so old data resolves, but participates in nothing. **Deprecation is not a soft delete of a still-live node; it is retirement into a read-only zone.**

### 9.3 What happens to non-conforming instances — the honest answer

**No standard answer, because it depends which kind of schema you have:**

- Under a **semantic schema**, instances cannot "fail to conform." An open-world ontology has no notion of an instance violating it; it either entails new facts or becomes inconsistent as a whole. **Neither localises to "this row is bad."**
- Under a **validating schema**, non-conformance is exactly what the report describes, per focus node, with severity and provenance. Re-running validation after a vocabulary change produces a delta. **This is why SHACL's non-mutating, idempotent design matters — you can re-validate history against a new schema version cheaply and safely.**
- PG-Schema's `LOOSE` mode is the third answer: legacy data that predates a type simply goes untyped rather than becoming invalid.

**The tradition's consistent counsel: deprecate, never delete; mint a new identifier when meaning shifts; keep stable identifiers separate from version identifiers.**

---

## 10. The open-world / closed-world question

### 10.1 Definitions

> "Under the **CWA** — what is not known is assumed false […] Under the **OWA**, it is possible for the relation to exist without being described by the graph."
> "**Ontologies typically adopt the NUNA and OWA.**"
> "A compromise is the **Local Closed World Assumption (LCWA)**, where portions of the data graph are assumed to be complete."

— Hogan et al., ACM Comput. Surv. 2021

**The unique-name axis matters too.** RDFS/OWL adopt **NUNA**; SHACL and ShEx adopt **UNA**. For an extraction pipeline producing surface-form-derived node identifiers, **UNA is almost certainly already in force**, making duplicate-concept detection a data-quality task rather than a logical one.

### 10.2 What goes wrong under each

> "The OWA and the CWA represent **extreme stances, and both have severe shortcomings. The OWA makes it impossible to answer 'No' to any query, while the CWA produces the answer 'No' also in cases where the KB should refrain from taking a stance.**"

— Razniewski et al., ACM Comput. Surv. 2024

**Why an LLM-extracted graph is structurally incomplete** — every cause applies to openCG:

> "(1) **Source incompleteness** […] (2) **Access limitations** […] (3) **Extraction imperfection**: Even statements that are available in digital form and accessible can be missed, because extractors are imperfect. This holds especially for automated text extraction methods: **The best models achieve only 75% in recall on the popular TACRED benchmark.** (4) **Resource limitations** […]"

**That 75% recall ceiling on a well-studied benchmark is the most useful single number in this section. An extracted graph's absences carry essentially no information about the world.** Roughly a quarter of the relations present in the text are simply not in the graph. **Any inference of the form "there is no `depends_on` edge, therefore no dependency" is unsound by construction — a fortiori for a 4-billion-parameter model on unconstrained prose.**

**The useful middle ground — the Partial Completeness Assumption:**

> "if a subject has at least one object for a given predicate, then there are no other objects in the real world beyond those in the KB. […] Empirically, the PCA has been found to be frequently satisfied."

And: "**if a predicate is asserted to be functional, then, per subject, presence of one object indicates completeness.**"

Empirical calibration: "some predicates are trivial to predict. These are obligatory attributes with only one or few objects per subject […] **Here, the CWA and PCA work great.** For the other relationships, the Popularity Assumption has a high precision, but low recall."

**Translated:** closed-world reasoning is safe exactly where a relation is functional or narrowly bounded, and unsafe where it is open-ended. **In openCG's ten-name edge vocabulary, `defined_in` is plausibly near-functional; `mentions` and `related_to` are unboundedly open. The right assumption is not uniform across the vocabulary — it is a per-relation property.**

### 10.3 The asymmetry to hold onto

- **Absence of evidence** is what an extracted graph produces in abundance, and it is nearly uninformative.
- **Evidence of absence** requires either a completeness assertion or a cardinality/functionality constraint. **Both are things a *deterministic* extractor can legitimately claim and a *chat-model* extractor cannot.**

**openCG's split extraction lands on both sides of this line.** Deterministic parsing of code can support genuine local closure ("these are all the `imports` in this file"). LLM extraction from prose cannot support closure on anything. **That is a factual consequence of the extraction method, and it is the sharpest thing the OWA/CWA literature has to say about this system.**

**Where the assumptions collide.** A validation layer is inherently closed-world while the graph being validated is inherently incomplete. **A `sh:minCount 1` constraint on an extracted graph does not detect a modelling error; it detects an extraction gap.** Both are worth knowing about, but they are different findings and conflating them makes the report useless. **This is the strongest argument in the literature for severity-graded, non-blocking reporting on presence constraints and stricter treatment of *contradiction* constraints — the former measures recall, the latter measures correctness.**

---

## 11. Worth borrowing

1. **The strict separation of validation from inference.** SHACL puts constraints and rules in separate vocabularies with separate invocation; RDFS fuses them, and that fusion is what makes `rdfs:domain` a trap.
2. **`sh:targetSubjectsOf` / `sh:targetObjectsOf` + `sh:class` as the shape of an endpoint constraint** — standardised, closed-world, per-edge-localised, and it names the two directions distinctly.
3. **The SHACL validation-result record** — `focusNode`, `resultPath`, `value`, `sourceShape`, `sourceConstraintComponent`, `resultMessage`, `resultSeverity`, `detail`. A decade-tested error schema.
4. **Three severity levels with the blocking decision left to the application.** The spec's honesty — severity has no effect on validation — is the feature.
5. **Validation as an idempotent, non-mutating function.** Makes re-validating history against a new schema version safe.
6. **SKOS's two-property pattern: assert direct links, derive the closure separately.**
7. **SKOS's refusal to make `broader` transitive.** `vehicles → cars → wheels`. In an automatically extracted hierarchy, mixed-relation chains are the norm.
8. **SKOS's documentation and labelling vocabulary** — `prefLabel`/`altLabel`/`hiddenLabel`, `definition`/`scopeNote`/`editorialNote`/`historyNote`, `notation`. `hiddenLabel` exists so misspellings feed a text index without appearing in a UI.
9. **PG-Schema's edge-type-with-endpoints (R2)** — the property-graph-native formulation, in the data model openCG uses.
10. **PG-Schema's `STRICT`/`LOOSE` × `OPEN`/`CLOSED` two-axis dial** — the standard way to introduce a schema into a graph that already has data.
11. **PG-Schema's type-vs-constraint locality test** — predicts which checks can run in a write path and which need a batch job.
12. **Rector normalisation as an *editorial* discipline: assert single parents, derive the rest.** (Note the automated derivation needs a reasoner.)
13. **OBO Principle 19's obsoletion protocol.**
14. **Stable identifier separate from version identifier.**
15. **`owl:deprecated` / `priorVersion` / `backwardCompatibleWith` / `incompatibleWith` as annotation vocabulary with no logical force.**
16. **LCWA / PCA applied per relation, not globally.**
17. **Interval or `ltree` path encoding — if and only if the hierarchy stays a tree.**
18. **Cycle detection by self-reachability in the closure.**
19. **`sh:condition` on rules: only derive from data that already validated.**
20. **Validating the validator's configuration.**

---

## 12. Traps

1. **Believing `rdfs:domain`/`rdfs:range` reject anything.** They entail. **Cost:** silent data corruption instead of an error; #2 source of newcomer error.
2. **Reusing the *names* "domain" and "range" for a validation mechanism.** Everyone who has touched RDF reads them with entailment semantics; everyone who has not reads them with SQL semantics. **Cost:** permanent ambiguity in every design document, code review, and bug report the project will ever produce, **for zero benefit — the validating tradition has its own perfectly good words.**
3. **Writing two `rdfs:domain` statements to mean "either."** They conjoin. **Cost:** intersection where you wanted union, silently.
4. **Expecting classes to be disjoint by default.** **Cost:** the only path from a violation to an *error* runs through disjointness.
5. **Reading SHACL severity as "warnings don't fail."** `sh:conforms` is false if there is *any* result.
6. **Reading `conforms: true` as "everything was checked."** It can equally mean nothing was targeted. **Report coverage.**
7. **Using a hierarchy edge as if it were transitive.** Mixed-relation chains manufacture false subsumptions in volume.
8. **Treating SKOS concepts as OWL classes.** Requires OWL Full, which is undecidable.
9. **Choosing a single-interval or single-path encoding and later permitting two parents.** **Cost:** the migration invalidates the storage format and every query written against it.
10. **Asserting a polyhierarchy by hand.** Documented cause of tangling in GALEN, SNOMED, GO.
11. **Adopting "single inheritance" as a hard model limit rather than an editorial discipline.**
12. **Deleting a class instead of deprecating it.** **Cost:** dangling references everywhere, no record of what happened.
13. **Changing what an existing class *means* while keeping its identifier.** OBO Principle 19 forbids exactly this. **Cost:** silent semantic drift; historical data classified under a term that no longer means what it meant, and nothing detects it.
14. **Leaving deprecated terms wired into the hierarchy.** OBO flags this as an ERROR.
15. **Reading absence in an extracted graph as absence in the world.** ~75% recall ceiling. **Cost:** `sh:minCount`-style constraints measure extraction recall while appearing to measure data quality.
16. **Applying one world assumption uniformly across a relation vocabulary.** **Cost:** either no constraint ever fires, or constraints fire constantly on relations that were never going to be complete.
17. **Expecting a property-graph engine to enforce endpoint types.** No system offers comprehensive schema support.
18. **Assuming Apache AGE behaves like Neo4j on labels.** AGE: at most ONE label per vertex. **Cost:** any multi-label scheme copied from Neo4j docs simply does not exist in AGE.
19. **Assuming AGE has declarative constraints.** No `CREATE CONSTRAINT`.
20. **Assuming the profiles form a ladder.** "none of the profiles is a subset of another."
21. **Underestimating how invisible an inference-caused failure is.** Contrast SHACL, where `sh:sourceShape` and `sh:sourceConstraintComponent` are mandatory fields on every result.
22. **Reusing terms from an external vocabulary without pinning a version.**

---

## 13. What requires a reasoner, a triple store, or expertise a small team will not have

### 13.1 Requires a description-logic reasoner
- Inferring a class hierarchy from logical definitions (the whole point of Rector normalisation)
- Subsumption between class *expressions*
- Consistency checking, and therefore any use of disjointness to detect violations
- **Explaining a conclusion** — justification tooling is a distinct product category
- Equality reasoning (`owl:sameAs`)
- Any use of OWL Full — undecidable

### 13.2 Requires a triple store

**Nothing on the borrowable list in §11.** This deserves emphasis because it is the most commonly assumed dependency and it is false. SHACL's constraint vocabulary, targets, severity levels and report structure are *concepts*. SKOS's two-property pattern is a table-design idea. PG-Schema's `STRICT`/`LOOSE` is a validation-mode flag. OBO Principle 19 is a workflow.

**You need a triple store if and only if you need RDF interchange.** Those are integration requirements, not ontology-layer requirements.

### 13.3 Requires expertise a small team will not have
- Choosing and staying inside an OWL profile (nobody checks the global restrictions by hand)
- Ontological normalisation (disjoint covering axioms, logical definitions, bridging modules)
- **Predicting axiom interaction.** The OWL 2 Primer on its own language: "It is a weakness because it is comparatively difficult for humans to immediately foresee the actual effect of various constructs in various combinations. […] **successful knowledge engineering often still requires some amount of training and experience**."
- Metamodelling

### 13.4 What is ordinary engineering, in Postgres, with no new dependencies
- Storing an asserted hierarchy (parent column, `ltree`, or closure table)
- Transitive closure (`WITH RECURSIVE`, or a materialised table refreshed by it)
- **Endpoint checking against asserted node classes** — a join from the edge to both endpoints' class columns, plus a lookup against allowed `(edge_type, subject_class, object_class)` triples, with subsumption if you closed the hierarchy. **This is `sh:targetSubjectsOf` + `sh:class` implemented as SQL. It is the single most important line in this section: the primitive under discussion is a join.**
- Cardinality and participation checks (`GROUP BY` / `HAVING`)
- Cycle detection (self-reachability in the closure)
- Severity-graded findings with structured results (a findings table with the SHACL result fields as columns)
- Deprecation and versioning (a `deprecated` boolean, a `replaced_by` FK, stable id distinct from version id, append-only history — **all of which openCG's existing audit-log discipline already resembles**)
- Uniqueness enforcement in AGE (a PostgreSQL unique index over the `agtype` accessor)

**The shape of the finding: essentially everything worth borrowing from the formal tradition is implementable as tables, joins and recursive CTEs. Essentially everything that requires a reasoner or a triple store is on the *inference* side of the validation/inference split — which is the side that produced the false-friend problem in the first place.**

---

## 14. Honest cost assessment for a team without ontologists

**Cost 1 — the learning curve is measured, and domain/range is on it.** Top two sources of newcomer error: open-world reasoning, then domain/range as axioms. **These are the first two things anyone touches.**

**Cost 2 — the failure mode is silence, not errors.** Every OWL/RDFS trap produces *wrong conclusions*, not *error messages*. A team without an ontologist has no mechanism for noticing.

**Cost 3 — debugging cost scales with ontology size, and there is no cheap tooling.**

**Cost 4 — worst-case complexity, and the fragility of staying tractable.** A team that cannot verify profile membership cannot rely on tractability.

**Cost 5 — the property-graph side offers no shortcut.** "no system offers comprehensive schema support." GQL v1's schema support is limited per its own editors; the standard is a 610-page paywalled ISO document. Neo4j's answer arrived 2026, Enterprise-only, Cypher 25-only.

**Cost 6 — Apache AGE gives nothing above labels.** One label per vertex, no constraint DDL, enforcement via hand-written PostgreSQL indexes. **Upside: what is left is plain relational engineering with well-understood costs, which is a better fit for a small team than a formalism nobody on it can debug.**

**Cost 7 — an ontology is a maintained artefact, not a delivered one.** GO doubled in five years while obsoleting ~25 terms/month. **Budget the maintenance, not just the build.**

**Cost 8 — external reuse imports someone else's release schedule.**

**Cost 9 — the incompleteness of the underlying data undermines a whole constraint category.** With ~75% recall as state of the art, presence and cardinality constraints on LLM-extracted relations measure extraction recall, not data quality. **Building them and treating their output as errors produces a permanently red dashboard, which is operationally identical to having no validation.**

### What is actually cheap

**The vocabulary and the patterns are nearly free; the machinery is expensive.** SHACL's result record, SKOS's asserted-vs-derived split, PG-Schema's `STRICT`/`LOOSE` dial, OBO's deprecation protocol, the validation/inference separation, and per-relation world assumptions all cost a design conversation and some table columns. **They require no reasoner, no triple store, and no ontologist.** The expensive things — inferred classification, consistency checking via disjointness, explanation tooling, profile discipline — are all on the *inference* side, and openCG's stated needs sit almost entirely on the *validation* side.

**The most valuable thing the formal tradition offers a team like this is not its machinery. It is thirty years of documented evidence about which distinctions matter, delivered as a vocabulary precise enough that the council can argue about the right thing.**

---

## 15. Source index

**W3C:** [RDF Schema 1.1](https://www.w3.org/TR/rdf-schema/) · [RDF 1.1 Semantics](https://www.w3.org/TR/rdf11-mt/) · [OWL 2 Primer](https://www.w3.org/TR/owl2-primer/) · [OWL 2 Profiles](https://www.w3.org/TR/owl2-profiles/) · [OWL 2 Structural Spec](https://www.w3.org/TR/2012/REC-owl2-syntax-20121211/) · [SHACL](https://www.w3.org/TR/shacl/) · [SHACL-AF](https://www.w3.org/TR/shacl-af/) · [SKOS Reference](https://www.w3.org/TR/skos-reference/) · [SKOS Primer](https://www.w3.org/TR/skos-primer/) · [ShEx 2.1](https://shex.io/shex-semantics/) · [ShEx vs OWL](https://www.w3.org/2001/sw/wiki/ShEx/ShEx_vs_OWL)

**Standards bodies:** [ISO/IEC 39075:2024 GQL](https://www.iso.org/standard/76120.html) · [gqlstandards.org](https://www.gqlstandards.org/) · [JTC1 explainer](https://jtc1info.org/wp-content/uploads/2024/04/2024-Article-39075-Database-Language-GQL.docx.pdf)

**Papers:** [PG-Schema](https://www.pure.ed.ac.uk/ws/portalfiles/portal/361128084/PG_SCHEMA_ANGLES_DOA02022023_VOR_CC_BY.pdf) · [Agrawal et al. 1989](https://doi.org/10.1145/67544.66950) · [Jin et al. 2008](https://www.cs.kent.edu/~jin/Papers/SIGMOD08.pdf) · [Hogan et al., Knowledge Graphs](https://aidanhogan.com/docs/knowledge-graphs-computing-surveys.pdf) · [Razniewski et al., Completeness/Recall/Negation](https://doi.org/10.1145/3639563) · [OWL Pizzas](http://www.cs.man.ac.uk/~rector/papers/common_errors_ekaw_2004.pdf) · [Rector, Normalisation](http://www.cs.man.ac.uk/~rector/papers/rector-Presented-at-Ontologies-for-Multi-Agent-Systems-Siguenza-Spain-2002.pdf) · [Hartung et al., OnEX](https://bmcbioinformatics.biomedcentral.com/articles/10.1186/1471-2105-10-250) · [Massive Problem of Remote Changes](https://doi.org/10.1145/3701716.3715478)

**Community:** [OBO Principle 19](https://obofoundry.org/principles/fp-019-term-stability.html) · [Validating RDF Data](http://book.validatingrdf.com/bookHtml013.html) · [ODP Normalisation](https://odps.sourceforge.net/odp/html/Normalisation.html) · [Mungall, SI considered dangerous](https://douroucouli.wordpress.com/2019/05/10/ontotip-single-inheritance-principle-considered-dangerous/)

**Engines:** [PostgreSQL ltree](https://www.postgresql.org/docs/current/ltree.html) · [Apache AGE Data Types](https://age.apache.org/age-manual/master/intro/types.html) · [apache/age #45](https://github.com/apache/age/issues/45) · [Neo4j Constraints](https://neo4j.com/docs/cypher-manual/current/constraints/) · [Neo4j Graph types](https://neo4j.com/docs/cypher-manual/current/schema/graph-types/)
