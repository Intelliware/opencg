# R3 — Empirical Evidence Dossier: Does a Typed Ontology Layer Actually Work?

**Role:** empirical-evidence researcher for design council
**Model:** Grok 4.5 @ high
**Question answered:** Does any of this (ontology-guided extraction, typed nodes, GraphRAG, small-model constrained extraction, confidence floors, HITL review, SHACL-style validation) actually work — with effect sizes, baselines, and disconfirming evidence?
**Scope constraint honored:** no openCG repo reading; no design recommendations.

---

## Executive finding (for the council)

The strongest honest answer is: **parts of the stack have measurable effects in isolation; the end-to-end claim "adding a typed ontology layer will improve this system" is under-evidenced for openCG's actual architecture** (hybrid text+vector retrieval today; graph not in the retrieve path; ~4B prose extractor; candidate→human promotion).

What has relatively solid evidence:

- Schema / type / relation constraints change extraction outputs and often raise *precision / schema-consistency / noise metrics*.
- Graph-augmented retrieval helps **some** multi-hop / global-sensemaking workloads and **hurts or ties** many single-hop / detail workloads vs strong dense or hybrid baselines.
- Classic IR shows **entity typing helps entity retrieval** substantially (oracle and automatic type detection).
- Verbalized LLM confidence is systematically overconfident; a raw 0.6 floor is weakly justified without calibration.
- SHACL-as-default validator is structurally blind to fabricated vocabulary under open-world semantics.

What is thin or missing:

- Controlled evidence that **typing nodes** (vs typed edges only) improves **RAG answer quality** on code/markdown corpora.
- Controlled evidence that ontology constraints on a **~4B** extractor improve **downstream retrieval/answer quality**, not just extraction F1 or shape.
- Controlled evidence that candidate queues for LLM-extracted facts are drained in production rather than abandoned.

---

## 1. Does schema-guided / ontology-guided extraction measurably improve extraction quality?

### What controlled comparisons show

**Yes for extraction metrics; mixed/unclear for "better facts" vs "differently shaped facts."**

| Study | Setting | Baseline | Delta | URL |
|---|---|---|---|---|
| RAP (Ye et al., 2022) | Relational triple extraction; schema-aware prompt components ablated | Full RAP prompt | On NYT/WebNLG with PRGC backbone, 5% data: RAP **78.74 / 47.26** F1 vs w/o Structure Info **75.52 / 44.85**; w/o Relation Info **77.79 / 46.05**. Larger relative drops at 1% data. | https://arxiv.org/pdf/2210.10709 |
| Xu et al. (2023) | Few-shot RE with LLMs | Text prompt / ICL without schema | "Adding schema information obtains much better performance"; generated GPT-3.5 data lifts prior SLM baselines by **+10.7 F1** (SciERC 16-shot) and **+6.6 F1** (RE-TACRED 16-shot). | https://arxiv.org/pdf/2305.01555v3 |
| CORE-KG ablation (2025) | Legal KGC; structured prompts vs GraphRAG-default prompts | Full CORE-KG | Removing structured prompts: **+73.33%** noisy nodes, **+4.29%** node duplication. Removing coref: **+28.25%** duplication, **+4.32%** noisy nodes. No gold-graph F1; quality is relative/proxy. | https://arxiv.org/html/2510.26512v2 |
| SPIREX / SPIRES family | Schema-constrained biomedical RE | Free LLM extraction | Schema-constrained SPIRES raises TP and lowers FP/FN vs GPT-3.5 / Llama-2 alone (figure-based; workshop paper). | https://vldb.org/workshops/2024/proceedings/LLM+KG/LLM+KG-12.pdf |
| OAK+MEND (2026) | Ontology consistency of LLM KG extraction on HotpotQA texts | Uncorrected OAK extraction | Triple ontology-consistency **63.4% → 96.8%** (Qwen3-30B) and **67.9% → 98.4%** (GPT-OSS-120B). Qualifiers **33.6% → 91.5%** / **35.7% → 96.8%**. **QA EM/F1: little or no loss** after correction — consistency ↑ without clear QA ↑. | https://arxiv.org/html/2605.29168v1 |
| AutoClusRE (preprint) | Type prompting + clustering | GPT-4o native RE | F1 **0.740 → 0.783** on HSA dataset. | https://doi.org/10.21203/rs.3.rs-7705090/v1 |

### Interpretation relevant to openCG

- Constraints reliably change **output distribution**: fewer illegal predicates, less type sprawl, less "legal noise."
- Ablations support that **relation info + structure info** matter for F1, especially in low-data / few-shot regimes.
- The best modern ontology paper that separates **consistency** from **usefulness** (OAK+MEND) finds large consistency gains and **no clear QA gain**. That is central: ontology adherence can be theatre relative to answer quality unless the graph is used in a way that rewards consistency.
- Many positive studies use **frontier or ≥8B models**, gold schemas (ChemProt, Wikidata), and extraction-F1 as the north star — not hybrid RAG over git corpora with a 4B model.

### Disconfirming / cautionary

- Constraint success is often measured as **schema validity / noise / consistency**, which can rise while semantic correctness falls (see §4 "constraint tax").
- CORE-KG and several GraphRAG KGC papers lack gold graphs; "better" = less duplication/noise vs another LLM pipeline.

**Claim strength:** Moderate that constraints improve extraction *shape and precision proxies*; **Weak** that they improve *downstream answer quality* for a hybrid-search system that does not yet consult the graph.

---

## 2. Does a knowledge graph improve RAG at all? (GraphRAG family + negative results)

### Positive results (with baselines)

| System / paper | Benchmark | Baseline | Reported gain | Caveat | URL |
|---|---|---|---|---|---|
| Microsoft GraphRAG (Edge et al., 2024) | Global sensemaking over podcast/news corpora | Naive vector RAG | ~**70–80%** LLM-judge win rate on comprehensiveness & diversity | No ground-truth answers; LLM-as-judge; task is **query-focused summarization / global themes**, not standard QA | https://www.microsoft.com/en-us/research/publication/from-local-to-global-a-graph-rag-approach-to-query-focused-summarization/ ; https://arxiv.org/abs/2404.16130 |
| HippoRAG (Gutiérrez et al., NeurIPS 2024) | Multi-hop QA | ColBERTv2 / RAPTOR / IRCoT | Up to **~20 points R@5** on 2WikiMultiHopQA; ~**3 points** on MuSiQue; QA F1 up to **+17** on 2Wiki, **+3** MuSiQue, **+1** HotpotQA; ~10–30× cheaper / 6–13× faster than IRCoT online | Gains concentrated on entity-centric multi-hop; HotpotQA weaker | https://arxiv.org/pdf/2405.14831 |
| LightRAG (Guo et al., EMNLP Findings 2025) | Large domain corpora | NaiveRAG / HyDE / RQ-RAG | LLM-judge win rates; authors claim widening gap on largest (Legal) set | Heavy reliance on LLM-as-judge win rates | https://aclanthology.org/2025.findings-emnlp.568.pdf |
| Sequeda, Allemang, Jacob (GRADES-NDA 2024 / data.world) | Enterprise insurance Text→query | GPT-4 zero-shot over SQL | Accuracy **16.7% (SQL) → 54.2% (SPARQL over KG)** | **Not RAG over documents.** Compares NL→SQL vs NL→SPARQL over a curated enterprise ontology. Vendor-affiliated authors. | https://arxiv.org/abs/2311.07509 ; https://doi.org/10.1145/3661304.3661901 |

### Strong disconfirming / mixed controlled evaluations

**Han et al., "RAG vs. GraphRAG: A Systematic Evaluation" (2025)** — best single source for the council:
https://arxiv.org/abs/2502.11371 / https://arxiv.org/html/2502.11371v3

Unified protocol, Llama-3.1-8B main results (Table 1 / Table 2):

| Method | NQ F1 | Hotpot F1 | MultiHop-RAG overall Acc |
|---|---:|---:|---:|
| **RAG (dense)** | **64.78** | 60.04 | 67.02 |
| RAPTOR | 60.04 | 61.31 | 68.78 |
| KG-GraphRAG (triplets only) | **34.28** | **25.02** | **41.24** |
| KG-GraphRAG (triplets+text) | 50.27 | 42.60 | 48.51 |
| Community-GraphRAG (Local) | 63.01 | 61.66 | 69.01 |
| Community-GraphRAG (Global) | 54.48 | 45.16 | 64.40 |
| HippoRAG2 | 61.03 | **63.01** | **70.27** |

Additional hard facts from the same paper:

- Answer-entity coverage in constructed KGs only **~65.8% (HotpotQA)** and **~65.5% (NQ)** → KG-only retrieval structurally cannot recover many answers.
- Retrieval accuracy (answer string in context): RAG **88.6 / 86.7** vs KG-triplets-only **39.2 / 32.2** (Hotpot / NQ).
- Cost (MultiHop-RAG): construction **135s (RAG) vs 7702s (KG-GraphRAG) vs 5560s (Community)**; retrieval time **1724 vs 14434 vs 1249**.
- Authors conclude RAG and GraphRAG are **complementary**; Community Global underperforms on detail-oriented QA, contrasting Edge et al.'s LLM-judge global-summarization wins.
- Position sensitivity of LLM-as-a-Judge is explicitly flagged as a reliability concern.

**GraphRAG-Bench / "When to use Graphs in RAG"** cites prior negative numbers: GraphRAG **13.4% lower accuracy on Natural Questions** vs vanilla RAG; **16.6-point** drop on time-sensitive queries; multi-hop depth **+4.5%** on HotpotQA at **2.3× latency** (citing Han 2025 / Zhou DIGIMON 2025):
https://arxiv.org/html/2506.05690v2

**Zhou et al., VLDB 2025 "In-depth Analysis of Graph-based RAG"** (DIGIMON): unified comparison; notes cases where Local GraphRAG **underperforms VanillaRAG** on complex QA datasets; RAPTOR often strongest among graph-ish methods:
https://www.vldb.org/pvldb/vol18/p5623-zhou.pdf

**Unbiased GraphRAG evaluation framework** (2025): LLM-judge position bias can reverse conclusions; after correction, previously reported large win rates shrink substantially (example cited in secondary reporting: **66.7% → ~39%**). Primary: https://arxiv.org/html/2506.06331v1

### Practitioner / engineering disconfirming evidence (weaker methodology, still informative)

| Source | Claim | Quality | URL |
|---|---|---|---|
| Yonk Labs GraphRAG-in-Postgres writeup | Vector+BM25 alone **75–90%** on bulk of questions; misapplied graph **subtracted 2–4%** by diluting ranking | Anecdotal / self-run; not peer-reviewed | https://yonk.dev/blog/graphrag-part1-vector-vs-graph/ |
| Ken Imoto switch-test | GraphRAG indexing **10–40×** cost of vector RAG; teams silently revert | Anecdotal | https://kenimoto.dev/blog/graphrag-vs-rag-7-step-switch-test/ |
| Mohammad Khan production critique | Index construction **40–57×** slower; per-query latency **14,434ms vs 1,724ms** (citing systematic benches) | Practitioner synthesis of papers | https://mohammadkhan.dev/blog/graphrag-pilots-succeed-production-fails |
| Hybrid stack GitHub claim | Vector-only overall **65.0%** vs GraphRAG **79.6%** vs hybrid **86.9%** on private 12K-doc set | Unreviewed vendor/personal benchmark | https://github.com/AniruddhaPKawarase/graphrag-hybrid-stack |
| FalkorDB / Diffbot marketing of KG-LM Accuracy Benchmark | **16.7% → 56.2%** (3.4×) | Vendor re-framing of Sequeda-style / Diffbot enterprise QA — **not hybrid document RAG** | https://www.falkordb.com/blog/graphrag-accuracy-diffbot-falkordb/ |

### Bottom line for §2

- **Graph helps when the query needs multi-hop association or corpus-level synthesis**, and when evaluation rewards diversity/comprehensiveness.
- **Graph often fails or underperforms when the query is single-hop / detail lookup**, when the extracted KG is incomplete (~1/3 answer entities missing), or when "graph" means triplets-only retrieval.
- For a system whose **current** retrieve path is hybrid text+vector and **does not consult the graph**, evidence that *building a better ontology* improves user-facing retrieval is **indirect at best**. The ontology can only help retrieval after the graph (or type filters) enter the retrieve/generate path.

**Claim strength:** Strong that GraphRAG is **not uniformly better**; Moderate that it helps **selected** multi-hop / global tasks; Strong that cost/latency/coverage are material.

---

## 3. Does node typing specifically help retrieval?

Distinguish carefully: **typed entities in entity search** vs **typed concept nodes improving RAG**.

### Strong evidence: type-aware *entity retrieval* (classic IR)

Garigliotti, Hasibi, Balog — *Identifying and exploiting target entity type information for ad hoc entity retrieval* (Information Retrieval Journal, 2019):
https://doi.org/10.1007/s10791-018-9346-x
Repo summary with numbers: https://github.com/iai-group/irj-types

- **Oracle** target-type distribution: up to **+67% relative NDCG@10** over strong text-only baseline (DBpedia entity search).
- **Automatic** target-type detection: **+44% relative NDCG@10** over same text-only baseline — sometimes matching or beating human-provided types.
- Earlier ICTIR 2017 analysis (*On Type-Aware Entity Retrieval*): type utility strongest with **large, fine-grained taxonomies** (Wikipedia categories >> shallow DBpedia/Freebase) and soft combination with term similarity; hard filters can hurt if types wrong: https://arxiv.org/pdf/1708.08291

Related: SIGIR 2017 target-type identification improves type recommendation for queries: https://ar5iv.labs.arxiv.org/html/1705.06056

LamAPI (OM 2022): hard/soft `rdf:type` filters change candidate ranking (qualitative Manchester/soccer-club example; coverage tables show filters reduce recall unless types are expanded): http://disi.unitn.it/~pavel/om2022/papers/om2022_LTpaper3.pdf

### Clinical / entity-augmented retrieval (adjacent)

CLEAR (npj Digital Medicine, 2024): entity-guided clinical note retrieval vs embedding chunk RAG — claims efficiency/relevance gains via NER + ontology expansion; domain-specific, not general code RAG:
https://www.nature.com/articles/s41746-024-01377-1

### What is *not* evidenced

I did **not** find a clean ablation of the form:

> same extracted graph, same retriever, **typed nodes vs untyped nodes**, measure RAG answer quality on hybrid search.

Most GraphRAG systems already extract entity/relation labels; papers rarely ablate **node class typing** separately from **having a graph at all**. HippoRAG's ablations emphasize synonymy edges / PPR / OpenIE quality more than a class taxonomy.

**Transfer caveat for openCG:** Balog-line results assume (a) entities already typed in a high-quality KB (DBpedia), (b) queries that are entity-seeking, (c) ranking entities not chunks. openCG's primary product surface today is **chunk retrieval for AI tools**, not entity cards. Typing may help *if* retrieve grows type filters / type-constrained traversal; that is a different proposition than "types improve extraction hygiene."

**Claim strength:** Strong for classic entity search; **Weak / extrapolative** for typed nodes improving openCG-style hybrid RAG.

---

## 4. How good are small (~4B) models at classification and constrained extraction?

### Classification into a fixed small label set

This is the task class where small models historically hold up best (N-way intent / category labeling).

- Comparative LLM text-classification study (OSF preprint): large aggregate accuracy gaps (~30pp) between smallest and largest models across many tasks/languages, but mid-size open models can match GPT-4 on some classification settings; **sub-~3B** models are often the clear weak cluster: https://doi.org/10.31219/osf.io/jvgc5_v1
- Practitioner/vendor tables claiming Gemma-3-4B / Phi-4 near GPT-4o on intent classification / JSON extraction (e.g., intent **93% vs 96%**, JSON **91% vs 97%**) are **not peer-reviewed** and should be treated as marketing-adjacent: https://masterprompting.net/blog/small-language-models-phi4-gemma-on-device-2026
- Fine-tuned Gemma-3-4B binary detectors can beat GPT-4o baselines on narrow tasks (e.g., AUROC **0.940 vs 0.92** on a 106-example AF benchmark) — shows capacity for narrow classification after fine-tuning, not zero-shot ontology assignment: https://huggingface.co/vincentoh/gemma3-4b-af-detector

**Honest read:** For a **small closed ontology** (tens of classes / ten relation types), a 4B instruct model is in the plausible competence band for *label selection*. Evidence quality for *zero-shot gemma3:4b specifically on openCG's ontology* is **absent** in the public literature I found.

### Constrained / JSON schema generation — the constraint tax

**The Constraint Tax** (2026), sub-3B / small-model structured outputs:
https://arxiv.org/html/2605.26128

Main suite (~15k generations):

| Mode | Schema validity | Answer accuracy | Wrong-valid-schema |
|---|---:|---:|---:|
| Prompt JSON | 61.5% | **19.7%** | 49.5% |
| Hard answer-only schema | **100.0%** | **11.0%** (−8.7pp) | **88.9%** |

Calendar tool-call analogue (both modes 100% schema-valid):

- Prompt JSON executable accuracy **91.5%**
- Hard schema executable accuracy **48.0%** (**−43.5pp**)

Authors' pattern: **reason free, constrain late**.

**SASS-Bench** (sub-1B): strict JSON / constrained decoding raises **schema pressure / false-fill** (fabricating required fields). Example SPI for Qwen3-0.6B **+0.485** under strict JSON: https://github.com/MohammadNuramin/sass-bench

**LLMStructBench** (structured extraction benchmark): Gemma3-1B competitive; notes that prompting/decoding strategy can matter as much as size; PJ+ (parse-force) raises validity at cost of semantic errors: https://doi.org/10.48550/arxiv.2602.14743

**TMLS synthesis** on constrained decoding: format tax concentrated on reasoning tasks; often smaller on pure classification/extraction: https://tmls.nyc/research/structured-outputs-constrained-decoding

### Relevance to openCG's 4B extractor

- Assigning an entity to one of N classes / picking a relation from a fixed 10-name vocab: **plausible** for 4B.
- Simultaneously extracting free-form spans, obeying domain/range, emitting JSON, and self-scoring confidence: **where small models degrade**, and where hard constraints can inflate *valid-looking wrong* triples.

**Claim strength:** Moderate that small models are OK at **narrow classification**; Strong that **hard constraints ≠ correctness** for SLMs; Weak for gemma3:4b specifically without a targeted eval.

---

## 5. Self-reported confidence / 0.6 floors — calibration or theatre?

### Peer-reviewed / arXiv evidence: verbalized confidence is poorly calibrated by default

**Xiong et al., ICLR 2024** — *Can LLMs Express Their Uncertainty?*
https://doi.org/10.48550/arxiv.2306.13063
https://proceedings.iclr.cc/paper_files/paper/2024/file/6733cf15e10e2cd1d59af033c3bb8507-Paper-Conference.pdf

Key results:

- Vanilla verbalized confidence: high **ECE** (authors cite averages **>0.377** for GPT-3 / GPT-3.5 / Vicuna class); confidence mass **80–100%**, multiples of 5.
- GPT-4 better calibrated but still weak at failure prediction: average **AUROC ≈ 62.7%** (near chance is 50%).
- White-box token-prob methods only narrowly better (example gap **AUROC 0.522 → 0.605**).
- Even after mitigation, professional-knowledge tasks remain hard.

**Tian et al., EMNLP 2023** — *Just Ask for Calibration*: for RLHF frontier models, **verbalized** confidences can beat token probs; Top-K + temperature scaling often **>50% relative ECE reduction**:
https://aclanthology.org/2023.emnlp-main.330.pdf
https://arxiv.org/pdf/2305.14975

This is **not** a free pass for a raw scalar field from a 4B local model. It shows elicitation method matters; vanilla "confidence: 0.7" in JSON is the weak case Xiong criticizes.

**On Verbalized Confidence Scores for LLMs** (2024): calibration depends heavily on *how* you ask; large models (≥70B) can get closer; still often ~10% ECE-scale deviation: https://arxiv.org/pdf/2412.14737

**Document extraction practice:** AgileDD reports TP and FP both scoring ~100% confidence — thresholds useless until a second calibrator is trained: https://www.agiledd.com/confidence-collaboration-problem-in-generative-ai-document-processing/

**Beyond Logprobs** (2026): logprob-mean / self-consistency alone are weak routing signals for field extraction (self-consistency AUC ~0.74 in their setting); multi-signal calibrators needed: https://arxiv.org/html/2606.24420

### Implication for a 0.6 floor

A fixed 0.6 threshold on model-written confidence, without:

1. reliability diagrams on *this* extractor + corpus,
2. ECE / precision-at-threshold,
3. separation of correct vs incorrect candidates,

is **weakly justified**. It may remove some low-confidence junk and also remove true positives while retaining fluent false positives at 0.9+. That is closer to **theatre with a filter shape** than a calibrated accept/reject policy.

**Claim strength:** Strong that uncalibrated verbalized confidence is overconfident; Moderate that *better elicitation + post-hoc calibration* can help; Strong that **0.6 without measurement is not evidence-based**.

---

## 6. Human-in-the-loop review economics

### Classic KB extraction HITL (closest analogy to candidate→confirmed)

**NELL (Never-Ending Language Learner)** — Carnegie Mellon:

- Candidate vs belief split; human review used to arrest concept drift.
- Overview: after human review sessions (~**5 minutes per category/relation** periodically), spot-check precision rose from ~**71% → ~87%**: http://rtw.ml.cmu.edu/rtw/overview
- Architecture paper budgets **10–15 minutes/day** human interaction: https://ojs.aaai.org/index.php/AAAI/article/download/7519/7380
- Follow-on work notes developers **limit verification to ~5 minutes/day** so the system remains "autonomous"; flagged edges otherwise pile up: https://archives.iw3c2.org/www2013/companion/p1195.pdf

NELL today reports tens of millions of candidates vs ~2.8M high-confidence beliefs — i.e., **most candidates are never human-confirmed**: http://rtw.ml.cmu.edu/

### Modern HITL queue evidence (mostly practitioner + queue theory)

| Source | Finding | Quality | URL |
|---|---|---|---|
| Tianpan, HITL bottleneck series (2026) | Reviewers become throughput limit; Little's Law: if arrival ≥ service, queue grows unbounded; rubber-stamp signature = review time ↓ while approval rate → 100% | Practitioner / engineering essay | https://tianpan.co/blog/2026-05-05-human-in-the-loop-throughput-bottleneck-ai-systems ; https://tianpan.co/blog/2026-04-23-hitl-queue-dynamics-approver-fatigue |
| Same author, capacity math | ~**90 items/reviewer/day** at 4 min/item × 6h; 3% escalate of 30k req/day → 900 escalations → ~10 FTE theoretical, 3–4× with peaks/PTO | Back-of-envelope, not measured study | https://tianpan.co/blog/2026-05-02-human-review-queue-is-your-p0-sla |
| Mavik Labs HITL guide | Target **10–15%** escalation; double-threshold routing | Practitioner checklist | https://www.maviklabs.com/blog/human-in-the-loop-review-queue-2026/ |
| arXiv 2605.27202 "Queue & AI" | AI assistance can lower mean human time but raise waiting time via heavier-tailed rework ("variance wedge") | Formal queueing model; limited empirical field data | https://arxiv.org/abs/2605.27202 |

### What makes review tractable vs abandoned (evidence-backed patterns)

Tractable in the NELL sense when:

- Ontology is **small and stable**,
- Review is **sampled / time-boxed**, not "drain all candidates,"
- Humans correct **blatant category/relation errors** that retrain extractors.

Abandoned / failing when:

- Arrival rate exceeds service rate (no shed/auto-resolve),
- Every extraction enters the same FIFO,
- Fatigue drives approval→credentialing,
- Staleness makes delayed confirmations useless.

**There is a scarcity of peer-reviewed throughput studies on LLM-extracted enterprise KG candidate queues.** The honest statement: **economics literature is thin; operational literature is consistent that unconstrained candidate queues do not get drained.**

**Claim strength:** Moderate (historical NELL) that light human feedback helps; Anecdotal/Moderate (ops) that queues clog; Weak on quantitative fatigue curves for KG fact review specifically.

---

## 7. Ontology-constrained validation in practice (SHACL-style)

### How many violations show up?

**OAK+MEND** (above): without correction, **~32–37% of triples** and **~64–66% of qualifiers** violate Wikidata ontology constraints on HotpotQA-derived extractions. Post-correction consistency >96% with little QA change: https://arxiv.org/html/2605.29168v1

That is the cleanest modern number for "LLM-extracted graph vs ontology."

### Are violations bad edges or bad types?

OAK's pipeline explicitly maps **entity types and predicates**, then symbolically detects violations and proposes corrective actions — i.e., failures are a mix of **wrong type assignment, wrong predicate, and domain/range mismatches**, not one exclusive class. The paper does not publish a simple "% type vs % edge" pie; the existence of both type-mapping and predicate-mapping stages implies both matter.

### SHACL's structural blind spot (critical)

**onto-correctness-bench** (Open Ontologies case study):
https://github.com/fabio-rovai/open-ontologies/blob/main/case-studies/onto-correctness-bench/README.md

Measured result:

- Across **3 real vocabularies**, **418 fabricated terms**, **300 graphs**:
  - Open-world SHACL: **`conforms=true` on 300/300** graphs containing fabricated terms.
  - Closed-world vocabulary gate: **flags 300/300**, **0 false positives** on clean graphs.

Interpretation: SHACL validates *shapes you wrote*, not *vocabulary existence*. An LLM that invents a plausible class/property sails through SHACL unless you also police closed vocabulary / domain-range explicitly. `sh:closed` is incomplete (doesn't police `rdf:type` class values well; brittle with imports).

Licensing-Oracle / SHACL-gated generation work shows interest in SHACL as a runtime gate, but is architectural more than a violation-rate study: https://arxiv.org/pdf/2511.06073

**Claim strength:** Strong that unconstrained LLM KGs have **high ontology-inconsistency rates**; Strong that **vanilla SHACL misses vocabulary hallucination**; Moderate that fixing violations improves consistency without necessarily improving QA.

---

## Strongest disconfirming evidence against "typed ontology layer → better openCG"

Ordered by how hard they hit the proposition:

1. **GraphRAG systematic evaluations show KG-triplet retrieval can catastrophically underperform dense RAG** (NQ F1 64.8 → 34.3; Hotpot 60.0 → 25.0) when the graph is incomplete (~65% answer-entity coverage). Source: https://arxiv.org/html/2502.11371v3
   → Building a prettier type system does not help if typed graphs still miss answer-bearing text.

2. **Ontology consistency can be raised dramatically without improving QA** (OAK+MEND). Source: https://arxiv.org/html/2605.29168v1
   → Typed constraints may produce "cleaner wrong" or "cleaner equivalent" graphs.

3. **openCG's retrieve path currently ignores the graph** (stated in brief). Until type-aware retrieve/generate is wired, ontology-layer wins are **hygiene / admin / future-enablement**, not measured retrieval gains.

4. **For small models, hard schema constraints can reduce semantic accuracy while raising validity** (constraint tax −8.7pp answer accuracy; −43.5pp executable accuracy in tool-call analogue). Source: https://arxiv.org/html/2605.26128
   → An ontology-shaped JSON schema on gemma3:4b may worsen factual extraction.

5. **Microsoft GraphRAG's headline wins are on global summarization judged by LLMs**, and later work shows judge position bias and underperformance vs RAG on detail QA with reference metrics. Sources: https://arxiv.org/abs/2404.16130 ; https://arxiv.org/html/2502.11371v3 ; https://arxiv.org/html/2506.06331v1

6. **Verbalized confidence floors are not calibrated filters** (Xiong et al.). Source: https://doi.org/10.48550/arxiv.2306.13063
   → A 0.6 gate does not substitute for ontology validation or human review.

7. **Node-typing's best evidence is entity search over curated KBs, not RAG over LLM-extracted concept graphs.** Source: https://doi.org/10.1007/s10791-018-9346-x
   → Extrapolation gap is large.

8. **HITL candidate queues historically are sampled, not drained** (NELL). Source: http://rtw.ml.cmu.edu/rtw/overview
   → Ontology + candidates does not imply a maintained gold graph.

---

## Evidence quality assessment

| Major claim | Rating | Justification |
|---|---|---|
| Schema/ontology guidance improves extraction F1 / reduces noise | **Moderate** | Multiple ablations (RAP, few-shot RE, CORE-KG, SPIRES). Mix of peer-reviewed and preprint; some lack gold graphs. |
| Ontology constraints improve *downstream RAG answers* | **Weak** | OAK shows consistency↑ QA≈flat; few end-to-end ablations on hybrid RAG. |
| GraphRAG beats dense/hybrid RAG in general | **Weak / False as universal** | Systematic benches show task-conditional wins; KG-only often loses badly. |
| GraphRAG helps multi-hop / global sensemaking | **Moderate–Strong** | HippoRAG (NeurIPS) + Microsoft GraphRAG (global QFS). Latter LLM-judged. |
| GraphRAG underperforms / is costly on many real workloads | **Strong** | Han et al.; Zhou VLDB; latency/cost tables; practitioner replications. |
| Node typing helps entity retrieval | **Strong** | Peer-reviewed IR (Balog line), large NDCG deltas with baselines. |
| Node typing helps openCG hybrid chunk RAG | **Weak / Anecdotal** | No direct controlled transfer study found. |
| ~4B models OK at small-N classification | **Moderate** | Broad classification literature + SLM practice; gemma3:4b-specific ontology eval missing. |
| Constrained decoding guarantees correct extractions for SLMs | **Strongly contradicted** | Constraint Tax; SASS-Bench false-fill. |
| Verbalized confidence ≥0.6 is a meaningful filter | **Weak (as currently used)** | Strong evidence of miscalibration; calibration possible with extra work (Tian). |
| Humans will drain candidate fact queues | **Weak / historically false at scale** | NELL samples; modern HITL ops warn of backlog/fatigue. Mostly non-peer-reviewed for LLM-KG queues. |
| SHACL catches LLM ontology hallucinations | **Strongly contradicted for open-world SHACL alone** | 300/300 miss rate on fabricated terms. |
| Sequeda 16.7→54.2 "proves GraphRAG" | **Misapplied if used that way** | Peer-reviewed workshop paper, but **Text-to-SPARQL vs Text-to-SQL**, not document RAG. Vendor-affiliated. |

Legend: **Strong** = multiple controlled evaluations or clear structural result; **Moderate** = solid papers but domain/transfer gaps; **Weak** = sparse, indirect, or contradicted for this use case; **Anecdotal** = blogs / single deployments.

---

## What would change my mind

| Current leaning | Evidence that would flip it |
|---|---|
| Ontology layer unlikely to improve *current* openCG retrieve quality | A controlled A/B on openCG corpora: hybrid retrieve **with vs without** type-aware graph expansion / type filters; report answer EM/F1 or human preference on a labeled query set matching real MCP traffic (≥200 queries, stratified single-hop vs multi-hop). |
| Constraints improve shape more than truth | Ablation on gemma3:4b: unconstrained vs schema vs schema+domain/range; measure **triple precision/recall against human gold**, not just schema validity. Show precision↑ without recall collapse. |
| Constraint tax will bite a 4B extractor | Show that for *this* narrow task (10 relations, small class set), constrained decoding is accuracy-neutral or positive (paired instances, report wrong-valid rate). |
| GraphRAG not worth it until hybrid is maxed | Demonstrate that after strong BM25+vector+rerank, graph path still adds ≥+5–10 absolute answer points on the multi-hop slice that is ≥X% of traffic — with cost/latency budgets. |
| Node typing is IR-legacy, not RAG-relevant | Typed vs untyped nodes, same edges/text links: significant NDCG/answer lift under type-aware retrieval. |
| 0.6 confidence floor is theatre | Reliability diagram on held-out extractions: precision of accepted tier ≥ target (e.g. 90%), ECE ≪ 0.1 after calibration; AUROC for correct-vs-incorrect ≫ 0.7. |
| HITL won't scale | Measured queue: arrival rate, service rate, abandonment, overturn rate, reviewer agreement; show stable drain at sustainable FTE with double-threshold routing. |
| SHACL-style validation is sufficient | Violation audit on real extractions showing SHACL (+closed vocab + domain/range) catches the dominant error classes with low false positives, and that removing violators improves downstream metrics. |

---

## Compact map: what "works" for which proposition

```
Ontology-guided extraction  → extraction F1 / consistency     YES (moderate)
Ontology-guided extraction  → better RAG answers              UNCLEAR / weak
Knowledge graph in retrieve → always better RAG               NO
Knowledge graph in retrieve → better multi-hop/global         SOMETIMES (moderate–strong)
Node types                  → better entity search            YES (strong, classic IR)
Node types                  → better chunk RAG                UNPROVEN
4B model                    → small-N classification          PLAUSIBLE (moderate)
4B model                    → hard schema + open extraction   RISKY (constraint tax)
Verbalized confidence threshold                               WEAK without calibration
HITL candidate→confirmed at scale        HISTORICALLY SAMPLED, not drained
SHACL alone over LLM graphs              INSUFFICIENT (open-world hole)
```

---

## Source index (primary URLs)

1. RAP schema-aware extraction — https://arxiv.org/pdf/2210.10709
2. Few-shot LLM RE + schema — https://arxiv.org/pdf/2305.01555v3
3. CORE-KG ablation — https://arxiv.org/html/2510.26512v2
4. OAK+MEND ontology correction — https://arxiv.org/html/2605.29168v1
5. SPIREX — https://vldb.org/workshops/2024/proceedings/LLM+KG/LLM+KG-12.pdf
6. Han et al. RAG vs GraphRAG — https://arxiv.org/html/2502.11371v3
7. GraphRAG-Bench / when to use graphs — https://arxiv.org/html/2506.05690v2
8. Zhou et al. VLDB graph-RAG analysis — https://www.vldb.org/pvldb/vol18/p5623-zhou.pdf
9. Microsoft GraphRAG paper — https://arxiv.org/abs/2404.16130
10. Unbiased GraphRAG eval — https://arxiv.org/html/2506.06331v1
11. HippoRAG — https://arxiv.org/pdf/2405.14831
12. LightRAG — https://aclanthology.org/2025.findings-emnlp.568.pdf
13. Sequeda et al. KG vs SQL — https://arxiv.org/abs/2311.07509
14. Garigliotti et al. type-aware entity retrieval — https://doi.org/10.1007/s10791-018-9346-x
15. On Type-Aware Entity Retrieval — https://arxiv.org/pdf/1708.08291
16. Constraint Tax — https://arxiv.org/html/2605.26128
17. SASS-Bench — https://github.com/MohammadNuramin/sass-bench
18. Xiong et al. confidence elicitation — https://doi.org/10.48550/arxiv.2306.13063
19. Tian et al. Just Ask for Calibration — https://aclanthology.org/2023.emnlp-main.330.pdf
20. onto-correctness-bench (SHACL hole) — https://github.com/fabio-rovai/open-ontologies/blob/main/case-studies/onto-correctness-bench/README.md
21. NELL overview — http://rtw.ml.cmu.edu/rtw/overview
22. NELL architecture (AAAI) — https://ojs.aaai.org/index.php/AAAI/article/download/7519/7380
23. Practitioner hybrid/graph underperformance — https://yonk.dev/blog/graphrag-part1-vector-vs-graph/
24. CLEAR clinical entity retrieval — https://www.nature.com/articles/s41746-024-01377-1

---

*End of dossier. No design recommendations offered.*
