# R4 — Failure-mode dossier: an ontology layer for openCG

**Model:** GPT-5.6 sol @ max

## Scope and evidence standard

Treats "ontology layer" narrowly: persistent node classes plus rules governing which relationship types may connect which classes. Does not assume RDF, OWL, a reasoner, or a universal upper ontology.

## Executive assessment

**"The Semantic Web failed" is too broad.** In a 2019 survey of 113 mostly expert, self-selected Semantic Web participants, a majority judged the original vision mostly or completely unrealized; the same respondents named schema.org, knowledge graphs, Wikidata, DBpedia, biomedical ontologies, JSON-LD, RDF, and SPARQL as successes. They broadly accepted lack of incentives, poor tooling, unreliable publishers, and verbose standards as valid criticisms. **The sample was recruited through a W3C mailing list and leaned academic — closer to an insider retrospective than an adoption survey, and probably optimistic rather than hostile.** ([Hogan et al., *The Semantic Web: Two Decades On*](https://www.semantic-web-journal.net/system/files/swj2229.pdf))

The central failure was **sociotechnical**. Research and standardization ran ahead of applications; publishers had no reason to incur semantic-authoring costs without consumers, while developers lacked data on which to build consumers. Peter Mika summarized the period as "research and standardization ahead of adoption" and "build it and they will come" ([Mika](http://ht.acm.org/ht2017/images/MikaPeterACM%20Hypertext%202017-WhatHappenedSemanticWeb.pdf)). Ora Lassila now lists agents, adoption, perception, ontology catalogs, easier editors, and good UX among what was missed; he says the focus on RDF's XML syntax delayed the effort by years ([Lassila ISWC 2024](https://www.lassila.org/publications/2024/lassila-iswc2024-keynote.pdf)).

**The evidence does NOT show that a small type vocabulary is inherently high-risk.** Application-bound vocabularies, simple type/property models, soft constraints, and faceted metadata have succeeded. **Risk rises when the vocabulary becomes authoritative, constraining, automatically populated, versioned as a public contract, and dependent on a human promotion queue.**

For a tiny, self-hosted project, the most dangerous failure is not "the ontology is philosophically imperfect." It is that **the ontology becomes a second product**: one needing definition owners, migrations, extractor calibration, documentation, review capacity, compatibility policy, and succession planning, while users expected a feature.

---

# 1. The Semantic Web retrospective

## 1.1 What the investment bought

DARPA's DAML program ran 2000–2006 and fed directly into OWL standardization ([DAML](https://www.daml.org/)). W3C created a dedicated Semantic Web Activity in 2001 with multiple working groups and several FTEs. The EU-funded Knowledge Web network alone had ~€7 million and 18 participating organizations ([CORDIS](https://cordis.europa.eu/article/id/95659-knowledge-web-network-of-excellence-to-realize-the-semantic-web-and-support-the-transition-of-/fr)).

This produced durable standards, tools, expertise, and domain systems. It did **not** produce the pervasive, decentralized agent ecosystem used to motivate the work. Lassila's 2024 retrospective says the agents are "not yet there" and that effective scope contracted from the Web to enterprise knowledge graphs.

## 1.2 What specifically failed

**Incentives failed before logic did.** Semantic publication imposed immediate local cost while promising diffuse future benefit. The application/data chicken-and-egg was identified at the time by James Hendler: users would not add markup without perceived value, and useful tools would not be developed without marked-up resources ([Hendler](https://www.cs.rpi.edu/~hendler/AgentWeb.html)). Schema.org later broke the deadlock by attaching structured data to a concrete consumer benefit — one vocabulary improving representation across multiple major search engines ([Guha, Brickley, Macbeth](https://queue.acm.org/detail.cfm?id=2857276)).

**Global agreement was overestimated.** Terms depend on purpose, jurisdiction, time, and stakeholder position. Formalization **exposes rather than eliminates** those disagreements. Ruben Verborgh argues semantics are consensus-bound and that publishers and consumers often quietly reinterpret formal ontology terms when the original consensus does not fit ([Verborgh](https://ruben.verborgh.org/articles/the-semantic-web-identity-crisis/)).

**Authoring burden was underestimated.** Interviews with 15 ontology authors found steep learning, information overload, and fragmented support for reuse, debugging, testing, maintenance. **One participant reported that domain experts stopped authoring as soon as the knowledge engineer disappeared, because databases and spreadsheets were easier** ([Warren et al.](https://doi.org/10.1016/j.ijhcs.2014.07.005)).

**Tooling was research-grade.** Many tools were academic prototypes built to demonstrate papers, poorly tested for usability, liable to disappear after research funding ended.

**Reliability assumptions did not match the open Web.** Logical inference treats asserted premises as true; longer inference chains compound exposure to bad premises. **This applies less strongly inside one controlled deployment, but reappears when automatically extracted facts are treated as authoritative.**

**Expressiveness carried computational and cognitive costs.** OWL 2 introduced EL, QL, and RL profiles specifically to trade expressiveness for tractable reasoning ([W3C OWL 2 Profiles](https://www.w3.org/TR/owl2-profiles/)). Historical evidence that "more semantic power" is not monotonically better.

## 1.3 Concrete failure stories

### Semantic Web Services and OWL-S

A 2007 web survey found only about **1,500 indexed semantic service descriptions** across OWL-S, WSML, WSDL-S, SAWSDL, with roughly **4% outside dedicated test collections**. The authors called the result disappointing given the research investment ([Klusch et al.](https://ceur-ws.org/Vol-243/SMR2-2007-paper6.pdf)). A practical OWL-S travel-agent implementation encountered "enormous difficulties," including OWL's poor fit for procedural knowledge ([Balzer et al.](https://www.uni-ulm.de/fileadmin/website_uni_ulm/iui.inst.090/Publikationen/2004/balzer-et-al-icsoc04.pdf)).

**A failure of over-ambitious automation and language fit. Does not predict that a flat set of concept types will fail.**

### FOAF

A contemporaneous W3C paper identified the bootstrapping failure: no critical mass of metadata without compelling applications, no applications without metadata ([Mika](https://www.w3.org/2001/sw/Europe/events/foaf-galway/papers/fp/bootstrapping_the_foaf_web/)). A later peer-reviewed history argues participants could not agree reliably on links, terms, or equality, and ordinary authors produced many broken cross-ontology links ([Halpin](https://journals.sagepub.com/doi/10.1177/20563051231195542)).

**FOAF's competitive context does not apply to a self-hosted enterprise tool. Its authoring and bootstrap failures do.**

### Sindice

A prominent linked-data search engine. In 2014 it entered read-only mode because **the original team had left the host institution or been assigned elsewhere**; its index stopped updating after 5+ years ([announcement](https://lists.w3.org/Archives/Public/public-lod/2014Jan/0080.html)). **A clean example of infrastructure whose useful state depended on a small team continuing to care for it.**

### Springer Nature SciGraph

Published ~1 billion RDF triples. Its former data architect reports that real-time SPARQL analytics and text search over the triplestore were inadequate; **loading took a week or more**, after which the team immediately extracted data for more usable systems. SciGraph was retired in 2023; Springer Nature **retained RDF for modeling** while storing JSON-LD in a document database ([Pasin post-mortem](https://www.michelepasin.org/blog/2023/02/03/rip-scigraph/index.html)).

**A runtime-architecture failure, not rejection of semantic modeling. The lightweight representation survived; the heavy serving layer did not.**

### Kadaster's linked-data knowledge graph

Especially relevant because it is neither dismissal nor vendor case study. Early datasets became **isolated RDF silos because nobody owned the linksets** connecting them. Transformation code grew too complex for domain experts to verify, while programmers patched problems they did not fully understand. Semantic models diverged from legally authoritative UML models and became unrecognizable to data owners. **External programmers accelerated delivery but took institutional knowledge with them when they left** ([Kadaster](https://semantic-web-journal.net/system/files/swj3749.pdf)).

**The failure was separating semantic modeling from authoritative ownership, enterprise architecture, and maintainable institutional expertise.**

---

# 2. Enterprise taxonomy and MDM failure

## 2.1 Do not trust the headline failure rates

Industry articles alternately attribute **75%** and **90%** MDM failure rates to Gartner. **Gartner's accessible guidance does not substantiate either universal percentage.** It says MDM initiatives often fail through lack of organizational readiness, confusion about what counts as master data, and belief in a software "silver bullet" ([Gartner](https://www.gartner.com/smarterwithgartner/how-to-get-started-with-master-data-management)). **The council should not repeat a dramatic universal failure rate whose denominator and methodology cannot be inspected.**

## 2.2 The "who decides what a Customer is?" problem is real

A 2015 study at multinational construction company **NCC**: four business areas lacked a unified vocabulary for `customer`, `supplier`, `project`; acquisitions compounded incompatible local meanings. Interviews identified common definitions, failed change initiatives, and data quality as dominant problems, **with most causes organizational and governance-related rather than technical** ([Eyob](http://www.diva-portal.org/smash/get/diva2:820629/FULLTEXT01)).

A peer-reviewed case study found a data team could not obtain consensus across divisions: stewardship policy had **no executive mandate, no power to act, unclear owners, low project priority**; data-improvement projects overran while political issues remained unresolved ([Cheong & Chang](https://aisel.aisnet.org/cgi/viewcontent.cgi?article=1110&context=acis2007)).

## 2.3 Nestlé: standard names did not dissolve organizational silos

Nestlé USA's six-year, $200M+ ERP effort. The company needed **18 months merely to reconcile item data so each division would call vanilla by the same code**. A rushed rollout produced **300 help-desk calls per day** and **77% turnover among demand planners**. The project had **"replaced divisional silos with process silos."** The CIO's conclusion: software installation without business-process change and universal buy-in is not implementation ([CIO post-mortem](https://www.cio.com/article/270680/enterprise-resource-planning-nestl-s-enterprise-resource-planning-erp-odyssey.html)).

**Transferable mechanism: a canonical vocabulary changes work and authority; technical agreement on identifiers does not settle who controls their meaning.**

## 2.4 Microsoft Viva Topics: AI did not remove taxonomy labor

Launched 2021 to use AI to organize enterprise content; **officially retired February 22, 2025** ([Microsoft notice](https://learn.microsoft.com/en-us/microsoft-365/topics/changes-coming-to-topics?view=o365-worldwide)). Microsoft attributes the retirement to its AI strategy, not publicly to failure.

The implementation record is more cautionary. **Microsoft's own adoption guide required at least one knowledge manager per participating business unit** to review, publish, merge, and remove suggested topics continuously ([adoption guide](https://adoption.microsoft.com/files/viva/topics/Microsoft-Viva-Topics-adoption-guide.pdf)). A practitioner retrospective describes a **"bootstrap conundrum"**: organizations expected AI to create the taxonomy, but the AI needed an organizational baseline and ongoing human curation most customers were unwilling to staff ([Reworked](https://www.reworked.co/knowledge-findability/viva-topics-is-dead-long-live-topics/)).

**Defensible conclusion: even a heavily funded AI-assisted product could not make organizational topic governance disappear.**

## 2.5 Transfer limits for openCG

Fortune 500 MDM failures are **not direct forecasts** for a single-tenant open-source knowledge catalog. MDM governs authoritative operational records across competing departments. A local openCG concept type may be advisory metadata with no power over a business process.

**The transferable risks are:**
- Somebody still owns each definition and its changes; otherwise policies exist without authority.
- Different self-hosting users can legitimately assign different meanings to the same word, so a supposedly universal default turns local variation into support and migration work.
- Automatic topic discovery does not remove the need to reconcile duplicates, scope, and false suggestions.
- **A vocabulary tied to no operational consumer becomes ceremonial rather than authoritative.**

---

# 3. The maintenance burden

## 3.1 Ontology change is normal, not exceptional

A longitudinal study of DBpedia, schema.org, PROV-O, FOAF examined **53 versions** and found additions, removals, hierarchy moves, abandoned terms in instance data, duplicate classes and properties. **None of the four communities followed the theoretical ontology-evolution frameworks in the literature** ([Mihindukulasooriya et al.](https://www.w3.org/community/owled/files/2016/11/OWLED-ORE-2016_paper_9.pdf)).

In a 2019 BioPortal study, **485 of 770 ontologies had multiple versions, totaling 15,025 recorded versions.** Reuse complicated maintenance because dependent ontologies did not consistently co-evolve ([Qawasmeh et al.](https://www.scitepress.org/Papers/2019/80647/80647.pdf)).

A 2025 BioPortal study found **100 of 759 ontologies — 13.17% — experienced potentially impacting changes from reused remote ontologies.** On average **15.78%** of an ontology consisted of remotely controlled terms in positions where their evolution could affect local consistency. Authors call these **lower bounds** ([Pernisch et al.](https://doi.org/10.1145/3701716.3715478)).

**For a self-contained local vocabulary, remote-reuse risk may be absent. Internal change propagation remains:** stored nodes, extraction prompts, validation rules, queries, UI filters, docs, APIs, and snapshots all become consumers of the schema.

## 3.2 There is no universal dollar price, but the work is measurable

ONTOCOM modeled ontology engineering as a lifecycle, calibrated on 36 and later 148 real projects. **It does not justify a universal claim that maintenance always costs more than construction.**

The durable ontology successes are backed by **institutions, not a one-off sprint**. A historical NIH award to the Gene Ontology Consortium totaled **$27.36 million** across its recorded 2001–2012 period ([HHS TAGGS](https://taggs.hhs.gov/Detail/AwardDetail?arg_AwardNum=P41HG002273&arg_ProgOfficeCode=55)). SNOMED International reported **50 total employees** at the end of 2024, operating recurring content, release, technical, governance, and member-support functions ([SNOMED 2024 annual report](https://www.snomed.org/_files/ugd/900274_ce2705fd34b04aa9a13cbfc1adcf8f39.pdf)).

**These are not cost comparators for openCG. They show that prominent "ontology success stories" are maintained public goods with recurring organizations and funding.**

## 3.3 What happens when the original author leaves

Four documented outcomes:

1. **The model freezes.** Sindice's index stopped updating when its team moved away.
2. **Tacit rationale is lost.** Kadaster's external programmers departed faster than internal staff acquired equivalent knowledge.
3. **The artifact survives but confidence falls.** Domain experts often return to spreadsheets once the supporting knowledge engineer disappears.
4. **Successors cannot reconstruct intent from structure alone.** Research on Chrome and Avaya found developer departures remove knowledge of prior decisions; abandoned files reduce successor productivity and increase mistakes ([Rigby et al.](https://dl.acm.org/doi/10.1145/2884781.2884851)).

Taxonomy practitioners identify the same single-point-of-failure pattern: once a project team is dissolved, one remaining taxonomist becomes irreplaceable ([Lippell](https://thesearchnetwork.com/good-practice-taxonomy-project-management-helen-lippell/)). Nike's taxonomy lead describes "painful learnings" where an owner vanished and the team scrambled to discover affected data and systems.

---

# 4. Over-modelling

## 4.1 The unused-class graveyard is observable

An analysis of ~650,000 Linked Open Data datasets found property hierarchies and most class hierarchies were shallow, while **approximately 67% of top-level class equivalence sets had no instances.** Authors cautiously interpret this as possible over-engineering beyond actual requirements ([Asprino et al.](http://arxiv.org/pdf/1906.08097v3)).

Schema.org shows the same pressure. In web crawls, **113 of 233 newly introduced classes and 109 of 389 properties in one change set were never observed through 2014.** Some absences reflected crawler blind spots, so unused does not always mean useless. Nevertheless most newly introduced elements were not significantly adopted ([Meusel et al.](https://www.uni-mannheim.de/media/Einrichtungen/dws/Files_Research/Web-based_Systems/pub/Meusel-etal-Schema-org-Adoption-WIMS2015.pdf)).

**The warning sign is not "many classes." It is a growing ratio of modeled distinctions to distinctions used in data, queries, interfaces, or constraints.**

## 4.2 More ontological clarity can reduce user performance

A controlled experiment compared a parsimonious logical data model with an "ontologically clearer" but larger model. Forty-five advanced commerce students with SQL training answered 14 queries. **At approximately twice the domain size used in earlier experiments, users of the clearer model made significantly more semantic errors, took longer, and were less confident** ([Bowen, O'Farrell & Rohde, ICIS 2004](https://aisel.aisnet.org/cgi/viewcontent.cgi?article=1095&context=icis2004)).

A database-query experiment, not an OWL study — should not be generalized mechanically. **It demonstrates a genuine trade-off: distinctions that make a model theoretically cleaner can increase what users must understand.**

## 4.3 There is no defensible universal tipping point

Stanford's guide states there are **no hard rules** for subclass counts. Many well-structured ontologies have roughly two to twelve direct subclasses, but this is a **diagnostic heuristic, not a limit** ([Noy & McGuinness](https://protege.stanford.edu/publications/ontology_development/ontology101-noy-mcguinness.html)).

Research on ontology complexity rejects size or class count as sufficient metrics — complexity is multidimensional ([Zhang, Li & Tan](http://hongyujohn.github.io/JSS_Ontology.pdf)).

**There is no evidence-backed answer such as "20 classes is safe" or "depth four is too deep." The practical tipping point is reached when ordinary maintainers can no longer predict the consequences of a change, users cannot select a class consistently, or modeled distinctions have no consumer.**

## 4.4 A concrete maintenance collapse: Cyc and the Open Directory

A Cyc integration project mapped **more than 10,000 Open Directory classes** using skilled knowledge workers. Because Open Directory identifiers were **not preserved when editors refactored categories**, mapping maintenance grew continuously and became **"insurmountable"**; Cyc removed the mappings until customer demand or full automation justified restoring them ([Reed & Lenat](https://courses.cs.umbc.edu/691s/papers/mapping-ontologies-into-cyc_v31.pdf)).

**The failure was the product of size, external change, unstable identity, and insufficient consumer value to pay for remapping.**

## 4.5 Expressiveness expands the failure surface

OWL 2's lightweight profiles exist because combining more constructs can change reasoning from tractable to multi-exponential or undecidable.

Gruber's **"minimal ontological commitment"**: a shared ontology should make as few claims about the world as necessary for its intended communication task ([Gruber](https://tomgruber.org/writing/onto-design.pdf)). **Over-modelling is not a new anti-ontology argument; it is a failure mode recognized inside ontology engineering.**

---

# 5. The empty-queue and abandoned-review problem

## 5.1 A review queue is a capacity system, not a UI feature

If candidates arrive faster than humans resolve them, backlog and feedback delay necessarily grow. Work on "learning to defer" explicitly models the interaction among classification, admission to human review, scheduling, time-varying arrivals, limited reviewer capacity, delayed labels, and selective sampling. **Fixed confidence thresholds ignore all of these interactions** ([Lykouris & Weng](https://arxiv.org/pdf/2402.12237)).

**Queue length alone is ambiguous.** An empty queue may mean reviewers kept up, admission thresholds silently excluded difficult cases, candidates expired, or nobody generated reviewable candidates. Oldest-item age, arrival rate, completion rate, admission coverage, and the distribution of reviewed vs unreviewed examples are more revealing.

## 5.2 Wikipedia New Page Patrol: difficult cases accumulate

In 2017, English Wikipedia's New Page Patrol had **almost 22,000 unreviewed articles, some waiting five months.** The Wikimedia Foundation found the backlog consisted mainly of **marginal, time-consuming cases** — not obvious spam. Review instructions encouraged people to leave a page for somebody else if they could not complete all checks, **concentrating precisely the ambiguous cases in the queue.** Active reviewers had fallen from the high 900s to the mid-300s after qualification rules changed ([WMF analysis](https://en.wikipedia.org/wiki/Wikipedia:New_pages_patrol/Analysis_and_proposal)).

Backlog drives temporarily worked, but **labor was extremely concentrated. In one drive, fewer than 10% of reviewers performed 90% of reviews**; once the drive ended, the backlog rose again. At another point, **two users performed 80% of review work among roughly 700 permission holders** ([NPP newsletter archive](https://en.wikipedia.org/wiki/Wikipedia:New_pages_patrol/Newsletter/Archive)).

**This is close to openCG's candidate problem: obvious cases clear; borderline entities, duplicate concepts, unfamiliar domains, and claims requiring source inspection remain.**

## 5.3 FlaggedRevs: a working filter can still become operationally untenable

Wikipedia's FlaggedRevs held edits for approval before publication. A cross-language study found it effective at keeping low-quality content out of public view ([Tran et al.](https://dl.acm.org/doi/10.1145/3555225)).

A later mixed-methods study explains why many communities reduced or rejected it. **In 11 language editions, review-time distributions were highly skewed; 95th-percentile waits reached dozens to hundreds of days.** Smaller communities described backlogs as **effectively unrecoverable**. As pending edits accumulated, **readers saw increasingly outdated "stable" versions**; some communities displayed unreviewed versions instead, sacrificing the feature's principal benefit ([restructuring study](https://par.nsf.gov/servlets/purl/10565773)).

**A promotion gate can fail in two opposite ways: block current knowledge behind stale confirmed state, or allow candidate state through and make "confirmed" operationally meaningless.**

## 5.4 The reviewed subset becomes unrepresentative

The **selective-labels problem** is formally established: when outcomes are observed only for cases selected by an existing decision process, the labeled cases are not a random sample and ordinary evaluation becomes misleading ([Lakkaraju et al.](https://pmc.ncbi.nlm.nih.gov/articles/PMC5958915/)).

Wikipedia's ORES illustrates a concrete distortion: **false-positive rates were significantly higher for newcomer and anonymous edits**, so model-guided review could disproportionately scrutinize those groups ([ORES Explorer](https://doi.org/10.1145/3461778.3462099)).

## 5.5 Human review is not automatically independent

A 2025 preregistered preprint with **2,784 annotators** found that making corrections more burdensome reduced correction behavior, attitudes toward AI strongly predicted accuracy, and **performance bonuses did not fix the problem.** Shared pre-annotations can make multiple human reviewers **repeat the same systematic machine error**, making inter-rater agreement look better than actual quality ([Beck et al., *Bias in the Loop*](https://arxiv.org/html/2509.08514v1)). Recent preprint on a specific task — treat as controlled evidence of a mechanism, not a universal effect size.

The Gene Ontology Consortium reports a related warning: **LLM-generated ontology definitions could be plausible but subtly wrong, and some errors were noticed only by more expert curators** ([GO 2026](https://pmc.ncbi.nlm.nih.gov/articles/PMC12807639/)).

## 5.6 What made review sustainable where it worked

- Wikipedia's scaled-back **Pending Changes** limits prepublication review to selected pages; trusted users' work bypasses review.
- Large-scale commercial moderation uses thousands of paid reviewers, queue simulation, capacity planning, skill-aware routing ([Meta QUEST](https://ar5iv.labs.arxiv.org/html/2103.16816)).
- **ASReview's active-learning workflow makes every human label train the next prioritization step**, records full state for transparency, and is designed to minimize manual screening rather than collect approvals ([van de Schoot et al.](https://doi.org/10.1038/s42256-020-00287-7)).
- Gene Ontology couples expert curation to purpose-built interfaces, evidence, quality checks, and a funded international consortium.

**The common property is not "humans in the loop." It is bounded demand, recognized labor, useful context, and a feedback path by which review reduces future work.**

---

# 6. Lightweight alternatives that beat heavy ones

## 6.1 Tagging versus taxonomy: task-dependent

Two controlled experiments found tagging could be faster during one organization task but more frustrating; taxonomies were faster in another setting but required more retrieval clicks. **Neither dominated every outcome** ([Pak et al.](http://blogs.clemson.edu/catlab/files/2021/09/Pak-et-al.-2007-Information-organization-and-retrieval-A-comparison-of-taxonomical-and-tagging-systems.pdf)).

A review reports folksonomies beat directories for news search but trailed general search engines and performed poorly for factual and exact-site queries ([ISKO](https://www.isko.org/cyclo/tagging)).

In a small cultural-heritage experiment (16 participants), combining folksonomic and controlled metadata made image finding **about six times faster** than controlled metadata alone; **88% of contributed tags were judged accurate** ([Trant](https://doi.org/10.63744/u3wqswmu8jag)).

Free tags carry documented ambiguity, synonymy, spelling, and specificity problems — `port` can denote wine, a harbor, a ship side, or a network endpoint ([Peterson](https://doi.org/10.6017/ital.v26i3.3272)). **They avoid governance work by moving disambiguation cost into search and users.**

**The strongest empirical pattern is complementarity:** free text and tags improve recall and match user language; controlled facets improve precision, navigation, and aggregation.

## 6.2 Explicit facets still earn their keep

A faceted-search experiment found significantly better efficient access, search success, flexibility, content understanding, relevant results, and satisfaction than single-classification ([Uddin & Janecek](https://doi.org/10.1108/14678040710748058)). A study using **1.5 million search logs** plus a user experiment found facets improved accuracy, especially on open-ended and difficult exploratory tasks, **but did not shorten search time** ([Niu et al.](https://asistdl.onlinelibrary.wiley.com/doi/10.1002/asi.23227)).

**Evidence for lightweight classification where users actually browse or filter by it. Not evidence for domain/range constraints or a deep class hierarchy.**

## 6.3 Can embeddings replace explicit types?

For similarity retrieval, often yes. But neural retrieval has documented difficulty with compositional distinctions such as negation. **On the NevIR benchmark, most first-stage neural retrievers — including state-of-the-art systems — performed at or below random ranking when two documents differed only by negation** ([Weller et al.](https://doi.org/10.48550/arxiv.2305.07614)).

Similarity also supplies **no durable declaration** that a node satisfied a class at a given version or that an edge was valid under a named rule.

**Embeddings replace some indexing distinctions, not integrity, deterministic joins, provenance, or stable filters.**

## 6.4 Can an LLM classify at query time instead?

**Evidence it can work:** a 900-article, 17-review dataset found a multi-model, confidence-weighted zero-shot framework reached **macro-F1 0.796**, comparable to human reviewers on that task ([Cambridge study](https://www.cambridge.org/core/journals/research-synthesis-methods/article/large-language-modelbased-paper-classification-framework-with-keyinsight-extraction-and-confidenceweighted-voting/BF9B4D6D81FC834F2D654E4F26FEB37B)).

**Evidence it is not a stable semantic contract:**
- A preregistered GPT-4 systematic-review study found apparent human-level accuracy was **inflated by class imbalance and chance agreement**. After adjustment, performance was generally none-to-moderate except under carefully engineered prompts ([Gartlehner et al.](https://ar5iv.labs.arxiv.org/html/2310.17526)).
- In a 14-class biomedical study, **fine-tuned BERT exceeded F1 0.8 while GPT-3.5 and GPT-4 were around 0.6**; advanced prompting did not close the gap ([StudyTypeTeller](https://pdfs.semanticscholar.org/0261/ea35d5acf2d43c4e8ca57fdbab7b110677e3.pdf)).
- Zero-shot classification changes with label wording and order. One study improved performance **from 0.54 to 0.76 solely by changing label options** ([LOADS](https://doi.org/10.18653/v1/2025.emnlp-main.1617)); another found **option-order sensitivity gaps up to 85%** ([NAACL](https://aclanthology.org/2024.findings-naacl.130.pdf)).
- Hosted models can produce materially different results under nominally deterministic settings; a 2025 evaluation found **instability even at temperature zero** ([Eval4NLP](https://aclanthology.org/anthology-files/pdf/eval4nlp/2025.eval4nlp-1.12.pdf)).

**Query-time classification can substitute for a stored type when the result is ephemeral, low-stakes, and used for ranking or conversational interpretation. It is not equivalent when two clients must obtain the same answer later, a constraint must be enforced before writing, or an auditor must know which rule accepted an edge.**

---

# 7. Premature schema

## 7.1 Why schema-last gained ground

Evolutionary database design starts from the premise that requirements cannot be fixed upfront. Fowler and Sadalage report versioned migrations, CI, testing, and incremental refactoring across hundreds of projects. **The point is not "never model"; it is that schemas can evolve safely when change is treated as normal engineering work** ([Fowler](https://martinfowler.com/articles/evodb.html)).

Biology supplies a domain example. The Chado genome schema paper notes a schema built around the former **"one gene codes for one enzyme"** understanding would be much simpler — and wrong for later molecular knowledge ([Mungall et al.](https://doi.org/10.1093/bioinformatics/btm189)).

## 7.2 Where schema-on-read failed

Raw data lakes often **deferred** schema work rather than eliminating it. The Lakehouse paper describes Delta Lake, Iceberg, and Hudi **reintroducing** transactions, schema enforcement, constraints, audit controls, and quality checks over object stores because customers found those controls necessary ([Armbrust et al.](https://www.cidrdb.org/cidr2021/papers/cidr2021_paper17.pdf)). Delta Lake's production account says schema enforcement **caught many wrong-schema appends** that had previously been difficult to trace ([Delta Lake VLDB](https://www.vldb.org/pvldb/vol13/p3411-armbrust.pdf)).

Shippable's CEO published a concrete post-mortem: MongoDB reached 4 TB; with 40+ developers and evolving document shapes, application code accumulated checks for absent fields. He estimated **90% of crashes involved code expecting a field that an older document lacked.** Backfilling a new mandatory field caused **more than four hours of downtime**, after which they moved to PostgreSQL ([Cavale](https://dzone.com/articles/why-we-moved-from-nosql-mongodb-to-postgresql)). First-hand opinion rather than controlled comparison, but specific and falsifiable.

**The historical result is not "schema last beat schema first." It is:**
- Early, rigid, speculative schemas can encode misconceptions and block learning.
- Permanently schema-free operational data moves ambiguity and validation into every consumer.
- Successful systems **preserve raw evidence while allowing explicit contracts to emerge and evolve.**

## 7.3 Where premature-schema arguments do not apply

Schema deferral is weaker when invalid data can cause irreversible action, cross-system exchange requires stable meaning, compliance requires reproducibility, or queries depend on exact category membership.

**Premature commitment and absence of commitment are different failure modes.**

---

# 8. Small-team and self-hosting specifics

## 8.1 Why the risks intensify

Open-source maintenance research describes **"scalar debt"**: invisible issue triage, support, governance, and coordination accumulate as use grows. Maintainers reported exhaustion from constant reminders of work not being done ([Geiger et al.](https://stuartgeiger.com/papers/maintaining-scaling-foss-cscw2021.pdf)).

A study of **more than 36,000 open-source projects** found most relied on **one core developer**, **89% had lost a core development team at least once**, and **only 27% of abandoned projects later attracted a new core developer. Seventy percent of abandonment events occurred within the first three years** ([Miller et al.](https://doi.org/10.1587/transinf.2025edl8005)).

A separate empirical configuration study found **51.9% of one commercial storage system's parameters could be removed with little effect on observed users**; excessive knobs were associated with **620 reported configuration issues** ([Xu et al.](https://ece.uwaterloo.ca/~wshang/soen691/2016winter/papers/fse15.pdf)).

**A customizable ontology can become another large configuration language whose users did not intend to learn.**

## 8.2 Failure modes likely to be fatal at this scale

**An unowned schema.** If the sole person who understands class rationale leaves, the project cannot safely evolve constraints or migrate old data.

**An unbounded candidate queue.** If automatic extraction continuously creates typed candidates and human promotion is required for trust, a tiny maintainer base becomes the service bottleneck.

**Authoritative constraints over noisy extraction.** GO's expert curators found plausible but subtly wrong AI-generated definitions that only specialists detected. If such outputs are automatically constrained, either valid but unusual facts are rejected or exceptions proliferate until enforcement loses meaning. **Wikidata's answer at massive community scale is mostly report-oriented property constraints, complete with exceptions and unresolved violations, rather than assuming every constraint can block every write** ([Wikidata constraints](https://www.wikidata.org/wiki/Help:Property_constraints_portal)).

**Per-deployment schema divergence.** Each customization dimension expands documentation, upgrade, migration, and support combinations.

**A schema with no consumer.** If retrieval, UI, audit, or integrations do not consume node types, the ontology grows without producing value.

## 8.3 Failure modes more likely to be annoying than fatal

- A few optional, visible type labels can be wrong without corrupting underlying source evidence.
- Unused classes create clutter but need not damage retrieval if not enforced.
- Local vocabulary differences reduce portability but matter less when deployments never exchange graphs.
- Soft constraint warnings can accumulate as debt without blocking ingestion.
- Query-time model classification can be inconsistent yet useful for exploratory ranking.

**The distinction changes once any of these labels become an API contract, authorization predicate, migration invariant, or prerequisite for retrieval.**

---

# 9. Early warning signs and tripwires

1. **Consumer deficit** — classes or constraints added without a named query, filter, validation outcome, or integration that uses them.
2. **Ghost-class growth** — the share of classes with no instances, no confirmed candidates, and no query references keeps rising.
3. **Constraint-exception growth** — violations and exceptions rise faster than the entities governed.
4. **Backlog instability** — candidate arrival exceeds completed reviews over sustained periods, and oldest-item age rises.
5. **Reviewer concentration** — a handful of people perform most promotions.
6. **Easy-case bias** — obvious candidates confirmed promptly while ambiguous domains age indefinitely.
7. **Coverage blindness** — quality metrics describe only reviewed candidates, with no account of what the extractor never admitted.
8. **Suspiciously high reviewer agreement** — humans almost always accept machine suggestions.
9. **Shadow vocabulary** — users create free tags, custom edge names, "other" classes, or local patches to bypass the official model.
10. **Change latency exceeds feature latency** — adding or correcting one concept requires prolonged debate, migrations, prompt changes, downstream coordination.
11. **Bus factor one** — only one maintainer can explain why a class exists or repair migrations.
12. **Docs/live-model divergence** — users are told to inspect the current graph because the documented schema is stale.
13. **Extractor changes silently reshape type distributions** — a model or prompt update causes sudden class-frequency changes without a domain change.
14. **Confirmed state becomes stale** — users rely on old confirmed facts because current candidates remain pending.
15. **Ontology work is justified by future possibilities rather than observed failures.**

---

# 10. The strongest case for doing nothing

The strongest argument is **not** that types are useless. It is that **persistent types and constraints have not yet earned their permanent cost.**

**First**, openCG already has explicit typed relationships, source text, embeddings, full-text-searchable material, and human-visible candidate status. A node type adds value only where an actual task cannot be served by relation types, retrieval, tags, or query-time interpretation. Semantic Web history shows that creating semantic supply before a consumer exists produces unused data and abandoned services.

**Second**, early-stage systems understand their domain least well at the moment they are most tempted to stabilize it. The "one gene–one enzyme" example shows how a clean early schema can encode yesterday's theory. Gruber's minimal-commitment criterion argues shared vocabularies should make only the claims required for current knowledge exchange.

**Third**, single-tenant deployment weakens one of ontology's strongest traditional benefits: cross-organizational semantic interoperability. Each operator can search its own corpus without reaching global agreement with strangers. **The global-agreement and decentralized-publisher problems that motivated RDF/OWL are therefore less relevant, while the maintenance costs remain.**

**Fourth**, automatic extraction plus human promotion turns every new semantic distinction into a **recurring labeling obligation**. A richer class system can increase ambiguous candidates faster than it increases useful confirmed knowledge.

**Fifth**, many occasional classification questions can be answered at query time. LLM and embedding approaches avoid migration and let interpretation reflect the current question. Their instability is unacceptable for integrity constraints but may be entirely acceptable for exploratory ranking.

**Sixth**, persistent classes become **versioned public surface area**. Renames, splits, merges, and endpoint-rule changes propagate into stored data, extractors, APIs, UI, tests, snapshots, and user customizations.

**Seventh**, the project's scarce resource is maintainer attention. **Every hour spent adjudicating whether `Library`, `Package`, `Module`, and `Service` are disjoint is an hour not spent improving ingestion, retrieval, observability, or reliability.**

**Finally**, deferral preserves the evidence needed to discover a later schema: source text, edge patterns, tags, queries, user behavior. Premature commitment is costly to reverse; continued observation is comparatively reversible.

**The strongest rebuttal is equally clear:** doing nothing forfeits stable facets, deterministic endpoint validation, consistent aggregation, and explicit semantic contracts. Faceted-search experiments and schema-enforcement post-mortems show those benefits are real. **The steelman therefore depends on a factual premise: that openCG does not yet have a demonstrated, valuable task requiring persistent node types rather than soft or query-time classification.**

---

# 11. What survived

## JSON-LD

Survived because ordinary web developers can use familiar JSON without learning RDF, SPARQL, or triple stores. Its co-creator says the specification was designed for web publishers and developers first and **to stand alone from the traditional RDF stack** ([Sporny](https://lists.w3.org/Archives/Public/public-linked-json/2011Sep/0000.html)).

**Measurable adoption:** in Web Data Commons' October 2024 crawl, **51.25% of 2.4 billion parsed pages contained structured data**; JSON-LD was the most-used markup format, present on **about 70% of sites that published structured data** ([WDC 2024](https://webdatacommons.org/structureddata/2024-12/stats/stats.html)).

## schema.org

Survived because it offered one shared vocabulary backed by multiple search engines, direct publisher incentives, a simple graph model, and **incremental evolution driven by deployed data**. Its designers **publish schemas early knowing they will change**.

**Its survival does not mean zero maintenance.** On its tenth anniversary, coordinator Dan Brickley asked the community to address **592 open issues** involving confusing, ambiguous, or inadequately documented terms ([schema.org technical debt](https://lists.w3.org/Archives/Public/public-schemaorg/2021Jun/0001.html)). **Lightweight success still incurs curation debt; it merely has strong consumers paying attention.**

## Wikidata

Deliberately chose a flexible, statement-centric data model with **no fixed schema imposed on concept groups**. Its creators identify both the advantage — broad, evolving participation — and the cost: persistent uniformity, coherence, and semantic-ambiguity problems ([Vrandečić & Krötzsch](https://doi.org/10.1145/3543873.3585579)).

Its property constraints are primarily surfaced as **reports with severities, clarifications, exceptions, and known violations** rather than universal write-time prohibitions. It also has a scale of community unavailable to a tiny project.

**What survived here was flexible collaborative structure plus soft quality machinery — not a small team maintaining a perfectly consistent formal ontology.**

## SKOS and lightweight concept schemes

Survived by representing thesauri and classification schemes **without forcing them into the stronger formal commitments of OWL**. Its design explicitly drew on minimal ontological commitment because traditional knowledge-organization systems are optimized for discovery and intuitive use, not mathematical theories of a domain ([Baker et al.](https://ar5iv.labs.arxiv.org/html/1302.1224)).

## Domain ontologies with strong institutions

Biomedical ontologies survived where the need was concrete, the consumer community was expert, and **recurring curation was funded**. **These successes establish that ontology can work. They also establish the organizational price of making it dependable.**

## RDF as a modeling or interchange layer

SciGraph abandoned its triplestore runtime but **retained RDF for modeling and JSON-LD for stored interchange**. The BBC similarly describes ontologies built incrementally against current business requirements rather than as a completed universal model.

**The semantic model survived when separated from the demand that one formal stack serve every operational workload.**

## Hybrid retrieval and metadata

Free tags adapt quickly but are ambiguous; taxonomies improve precision and navigation; search handles text that was never classified. **Faceted interfaces work best alongside direct search rather than replacing it.**

---

# Final risk statement

**The known failure is not "adding types." It is allowing a useful handful of types to turn into an authoritative worldview without a demonstrated consumer, a funded owner, bounded review demand, or a credible evolution story.**

The evidence supports a narrow conclusion rather than reflexive contrarianism:

- Lightweight, application-driven typing can be low-risk and useful.
- Formalism does not settle definitions, incentives, or ownership.
- Automatic extraction does not eliminate curation; it can create more of it.
- There is no universal safe class count or hierarchy depth.
- Embeddings and query-time LLM classification can replace persistent types for soft, ephemeral interpretation, but not for deterministic integrity.
- **At small-team scale, review capacity and succession are more likely to kill the effort than RDF, PostgreSQL, Apache AGE, or any particular constraint syntax.**
