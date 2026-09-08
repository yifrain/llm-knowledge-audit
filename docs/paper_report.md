# Context-Aware Entity Disambiguation and Factuality Auditing for LLM-Generated Knowledge

Yifan Li · M.Sc. Computer Science, Technische Universität Dresden

**Working report. Human review and real LLM experiments pending.**

## 1. Abstract

We implement a reproducible prototype for comparing string-only and context-guided entity linking,
then auditing factual triples associated with selected canonical subjects. The pipeline supports
public candidate retrieval, schema-validated generation, evidence-backed judging, blinded human
annotation, and explicit cost/failure tracking. Forty proposed cases and 113 public KB claims are
prepared for human review. Offline synthetic runs validate software behavior only. No claim about
real model accuracy or judge reliability is made before human verification and approved experiments.

## 2. Introduction

Identical entity strings can refer to different real-world objects; different strings can refer to
the same object. These ambiguities undermine factual audits: a true statement about a namesake
can be irrelevant to the intended subject. We separate identity correctness from evidential support
and preserve links connecting original mentions, resolution decisions, canonical triples and evidence.

## 3. Related Work

Hu et al. (2025), [Enabling LLM Knowledge Analysis via Extensive Materialization](https://aclanthology.org/2025.acl-long.789/),
materialize LLM knowledge to support broader analysis than predefined questions.
Hu et al. (2026), [Direct Construction of Disambiguated Knowledge Bases from Large Language Models](https://arxiv.org/abs/2608.03729v3),
address direct disambiguated KB construction; their [GPTKB 2.0 demonstration](https://arxiv.org/abs/2608.06992v2)
makes knowledge and decision provenance inspectable.
Giordano and Razniewski (2026), [Beyond Questions: Evaluating LLM's Knowledge Expression](https://arxiv.org/abs/2605.26937v2),
motivate open knowledge evaluation. Current source titles differ from two initial working citations.
Our external Wikidata-linking prototype does not reproduce internal GPTKB canonicalization.

## 4. Research Questions

RQ1 concerns context's effect on top-1 accuracy; RQ2 homonym separation and synonym merging;
RQ3 evidence-backed three-way factuality classification; RQ4 judge/human agreement; RQ5 cost,
latency, coverage and structured-output robustness. These are proposed questions, not established findings.

## 5. Dataset

The draft contains 40 cases (20 homonym and 20 synonym) across 30 proposed QIDs. All cases await human
verification. Metadata and ranked search candidates are separately stored with public provenance.
The convenience sampling and identifying contexts limit generalization. A separate packet contains
113 public KB-derived claims for annotation practice; it is not a generated-model evaluation set.
No human labels exist. At least 100 generated triples will require human annotation after approved runs.

## 6. Method

The baseline ranks normalized labels/aliases using string similarity, with deterministic ties and
abstention. The context method receives a non-gold mention/context/source-triple view plus candidate
metadata and emits a candidate ID or null. Both share retrieved candidates. Generation operates on
the union of selected QIDs, not gold IDs, with canonical-subject and schema validation. Duplicate
triples are removed. English Wikipedia API passages are retrieved via canonical sitelinks and ranked
lexically. A structured judge uses only bounded supplied evidence and explicit label definitions.
Human reviewers receive that identical evidence with predictions hidden.

## 7. Experimental Setup

Implementation uses Python 3.11+, typed Pydantic schemas, provider interfaces, immutable JSON artifacts,
content-addressed caches and deterministic mock fixtures. Source, data and configuration hashes,
prompt versions, model snapshots, seeds, failures, retries and operation metrics are recorded.
The planned five-case pilot uses GPT-4.1 mini for resolution/generation and GPT-4.1 for judging, with
at most 65 logical calls and USD 2 reserved spend. Execution requires explicit approval.
Metrics include coverage, per-pair identity measures, strict/decisive precision and three-way human
agreement. Descriptive intervals are not used to claim significance on clustered cases.

## 8. Results

**Software verification:** the offline pipeline has executed and produced synthetic artifacts.
Saved outputs and exact sample sizes are in `docs/mock_demo/`; they are not research findings.
The public source collection check retrieved proposed gold candidates for 38/40 draft cases; without
human verification, this is not final benchmark recall.

**RQ1–RQ5:** TODO: Insert measured result after running the approved experiment and human review.

| Research outcome | Status |
|---|---|
| Real context vs string accuracy | TODO: Insert measured result after running experiment. |
| Human-verified homonym/synonym outcomes | TODO: Insert measured result after running experiment. |
| Generated-triple factuality distribution | TODO: Insert measured result after running experiment. |
| Judge/human agreement and kappa | TODO: Insert measured result after human annotation. |
| Real latency/token/cost/validity trade-offs | TODO: Insert measured result after running experiment. |

## 9. Error Analysis

The saved public search snapshot misses proposed targets for `homonym_008` and `homonym_018`.
These are actual retrieval observations awaiting human target verification. Mock run reports contain
record-linked software-test errors; they must not be attributed to a real LLM. Temporal mismatch,
hallucinated relation and judge false-positive/negative causal analyses remain pending human review.
TODO: Insert concrete real-experiment disagreements and adjudicated error categories.

## 10. Limitations

Unverified convenience cases, no completed human labels, no executed paid experiment, English-only
retrieval, incomplete candidate coverage, lexical evidence ranking, uncalibrated confidence, correlated
observations and common-family generator/judge bias prevent strong conclusions. KB-derived practice
claims are not independent truth evidence. Full details appear in `limitations.md`.

## 11. Conclusion

The implemented artifact provides an inspectable foundation for a bounded entity-linking and
factuality study. Scientific claims require the next steps: verify cases, approve a pilot, annotate
actual generated triples, and report measured outcomes with coverage and limitations.
