> Advanced implementation reference. Current default scope: 5 pilot cases, an optional 12-case comparison, and at most 20 initial human fact labels. Earlier 40-case/100-label targets below are optional extensions. Start with README_CN.md.

# Context-Aware Entity Disambiguation and Factuality Auditing for LLM-Generated Knowledge

**A research prototype by Yifan Li · M.Sc. Computer Science · TU Dresden**

Does relational context help distinguish *Mercury the planet* from *mercury the element*?
And when an LLM judges a generated fact, does its decision agree with a human reading the same evidence?
This small Python project makes these questions testable through explicit candidate sets,
versioned prompts, traceable evidence, and reproducible evaluation.

**Status: implemented and tested research infrastructure; human validation and paid experiments pending.**
The scientific MVP is **not yet complete**: there are 40 source-checked **draft** entity cases,
113 public KB claims ready for review, and **zero human-verified cases / zero human labels**.
No paid LLM calls have been made. Mock outputs must never be cited as model performance.

## Motivation and related work

[Hu et al. (ACL 2025)](https://aclanthology.org/2025.acl-long.789/) motivate eliciting factual
knowledge as triples, allowing analyses beyond preselected question answering.
[GPTKB 2.0 construction](https://arxiv.org/abs/2608.03729v3) addresses canonicalization and
entity ambiguity; its [auditing demo](https://arxiv.org/abs/2608.06992v2) exposes the
provenance of disambiguation decisions. [Giordano and Razniewski](https://arxiv.org/abs/2605.26937v2)
motivate open knowledge evaluation. This project studies a bounded component of that agenda.
**It is an external Wikidata-linking experiment, not a reproduction of GPTKB's internal
canonicalization or million-scale construction.** Bibliography: [references.bib](../docs/references.bib).

## Research questions

1. Does context improve top-1 entity linking compared with strings alone?
2. Does it separate homonyms and correctly merge synonymous mentions?
3. Can an evidence-grounded judge distinguish entailed, contradicted, and insufficiently supported claims?
4. How well do judge decisions agree with independent human annotations?
5. What are the accuracy, coverage, latency, token, cost, and output-validity trade-offs?

## Run the offline demo

Python 3.11+ is required; Python 3.12 was used for the local checks.
The committed `uv.lock` fixes direct and transitive dependencies.

```bash
uv sync --frozen --extra dev --extra plots
source .venv/bin/activate
pytest
ruff check .
mypy src
llmka validate-data --config configs/mock.yaml
llmka run-all --config configs/mock.yaml
```

Installation needs package access once. After installation, the mock run needs **neither a key
nor network access**. Tests block sockets with `pytest-socket`. With pip, use
`python -m pip install -e '.[dev,plots]'` (compatible ranges; use the lockfile for exact reproduction).
Run commands from the project root. Config paths inside YAML resolve relative to the repository,
not the terminal's working directory. Shell scripts in [scripts/](../scripts/) are convenience wrappers.

The CLI prints a new `results/mock/<run-id>/` directory. Open its `report.md` and `evaluate.json`.
It also contains stage artifacts, a manifest, telemetry, checkpoints, and a blinded annotation packet.
A clean demo currently yields 145 synthetic triples across the union of 29 resolved entities.
Those are fixture claims such as `demo_value=alpha`, **not asserted real-world facts**.
The mock resolver uses lexical overlap and is not an LLM. All mock latency/token/cost counters
are defined as zero; measured system speed is not claimed. [Saved demo](../docs/mock_demo/report.md).

## Data and methods

The draft contains 20 homonym cases (10 pairs) and 20 synonym cases (10 pairs), covering 30
canonical entities and nine domains. All QID labels/descriptions were retrieved from Wikidata.
Gold fields remain proposed targets until human verification. Each record preserves its source
URL and retrieval time. See the [data card](../docs/data_card.md) and [review instructions](../data/benchmark/README.md).

Two candidate sources are deliberately separate:

- **Controlled mock fixture**: a small metadata-backed candidate pool for testing.
- **Public search snapshot**: actual ranked `wbsearchentities` results, enriched with aliases
  and descriptions. Gold IDs are never inserted. The source check found the proposed entity
  among the top ten in 38/40 drafts; this is a provisional collection check, not verified benchmark recall.

The string baseline sees only a surface form and candidate labels/aliases. NFKC normalization,
case folding, punctuation normalization, and RapidFuzz similarity determine its ranking. Exact ties
use lexicographic QID order. Context and descriptions cannot enter its typed input.
The context method sends the surface, independently authored context, source triple and candidate
metadata to a configurable provider. It accepts only a candidate QID or null, with a bounded
confidence and concise rationale. A threshold supports abstention. Neither method receives gold fields.

### Pipeline

```text
Draft/reviewed cases → Wikidata candidates → string + context resolution
                                              ↓
                           union of actually resolved canonical entities
                                              ↓
                      schema-validated generation → duplicate removal
                                              ↓
                     canonical Wikipedia sitelink → ranked API passages
                                              ↓
                           evidence-only judge → blinded human review
                                              ↓
                               metrics → error analysis → report
```

Generation is shared once per canonical entity and linked to every originating method/case.
This avoids repeated generation and makes the method-conditioned audit traceable. Entity linking
and factual truth remain separate: a true triple about a wrong sense does not count as joint success.
The MVP audits the canonical **subject**; generated object mentions are not separately linked.

Wikipedia evidence comes from official APIs using the selected QID's English sitelink, revision IDs,
serial requests, explicit timeouts, transient-only retries, rate limiting, and raw-response caches.
Whole passages are deduplicated and selected within a character budget. Missing evidence yields NEI;
malformed output or refusal is a failure, never silently converted into a valid judgment.
Conflicts are covered by judge instructions and a synthetic test; semantic conflict detection still
requires the judge and human review. OpenAI-compatible JSON-schema requests are implemented;
provider compatibility has been transport-tested, not paid-live-tested.

## Independent stages and resume

```bash
llmka collect-candidates --config configs/mock.yaml
llmka disambiguate --method string --config configs/mock.yaml
llmka disambiguate --method context --config configs/mock.yaml
llmka generate-triples --config configs/mock.yaml
llmka retrieve-evidence --config configs/mock.yaml
llmka judge --config configs/mock.yaml
llmka evaluate --config configs/mock.yaml
llmka build-report --config configs/mock.yaml
llmka run-all --config configs/mock.yaml --resume results/mock/<previous-run-id>
```

Every invocation creates a **new directory**. A stage executes missing prerequisites.
`--resume` copies successful immutable artifacts/checkpoints and never edits the parent run.
Changing configuration, source code, or benchmark inputs rejects resume. Changing human annotations
is permitted: evaluation and reporting are recomputed while model artifacts stay frozen. Resume also
carries forward conservative budget reservations, including attempted requests before interruption.
File-level caches permit fresh runs to reuse completed identical requests. Refreshing public data
requires a new cache directory and produces a new dataset version; experiments never rewrite gold.

## Human annotation

[data/annotations/human_annotations.template.jsonl](../data/annotations/human_annotations.template.jsonl)
contains **113 blank records** bound to the public KB review packet. These are source-derived
positive-biased practice records, **not an LLM-generated test set** and not a completed annotation study.
The actual human annotation file is empty.

Each model run creates its own `annotations.template.jsonl` and `annotation_packet.json` with
exactly the evidence the judge saw, excluding judge predictions. Review at least 100 actual
LLM-generated triples using the [annotation guidelines](../docs/annotation_guidelines.md). Fill reviewer
identity, date, notes, evidence IDs, and labels; retain the triple/evidence hashes. Point the unchanged
configuration's annotation file at those records, then resume evaluation. Never replace labels with
fixture or judge outputs. Different evidence snapshots and duplicate IDs are rejected.

## Metrics and interpretation

Metrics include candidate Recall@k/MRR; top-1 accuracy, abstention and conditional accuracy;
homonym separation/conflation and synonym merge rates; per-domain errors; valid JSON/schema,
duplicates and triples per seed; factual label proportions, strict and decisive precision;
judge accuracy, macro P/R/F1, confusion matrix and Cohen's kappa; latency percentiles,
API requests, token usage, estimated cost, retries and failures.
Every rate carries its numerator/denominator; unavailable values are null. Case Wilson intervals
are descriptive because ambiguity groups are dependent. Macro metrics use all three labels with
an explicit zero-division convention. See [metric definitions](../docs/metrics.md).

Automatically flagged examples are generated only from actual run records. Categories such as
hallucinated relation and temporal mismatch remain marked **requires human error review** until
reviewed; an empty flag list does not prove zero errors.

## Real pilot: approval required

```bash
llmka pilot-plan --config configs/pilot.yaml
```

The [pilot proposal](../docs/pilot_proposal.md) specifies five cases, exact model snapshots,
call/token estimates and a USD 2 cap. First review those five case records. Set `LLMKA_API_KEY`
in your environment without printing it. After explicit approval:

```bash
llmka run-all --config configs/pilot.yaml --approve-paid
```

No stored key or `.env` auto-loader is included. The application refuses unapproved uncached calls,
reserves a conservative cost before every attempt, and enforces request and budget caps. Price
estimates must be revisited before execution. Reservation can stop a run earlier than actual usage
would require. For replay, set `offline: true` in a new configuration and use cached requests.
The initial five-case pilot is a technical smoke experiment, not a statistically persuasive study.

Once a real run exists, `llmka plot --run-dir results/real/<run-id>` writes a fresh figures directory
with PNGs and machine-readable sources. Mock runs are rejected. Human confusion matrices are
omitted until annotations exist. No real-result figures or CV achievement bullets exist yet.

## Implemented, completed, and pending

| Category | Status |
|---|---|
| Typed pipeline, providers, cache, CLI, resume, metrics, reports | Implemented and tested offline |
| Public candidates / source metadata | Collected; provenance saved |
| Benchmark verification | 0/40 human verified; pending |
| Public-claim review template | 113 unlabeled records; ready for review |
| LLM-generated factuality experiment | Pending approval and execution |
| Human annotation study | 0 completed; at least 100 generated triples required |
| Real plots and measured CV bullets | Pending real results |

[Paper-style report](../docs/paper_report.md) · [Research plan](../docs/research_plan.md) ·
[Protocol](../docs/experiment_protocol.md) · [Limitations](../docs/limitations.md).

## Ethics and licensing

Code is independently written from scratch under MIT. No proprietary employer code, prompts,
data, endpoints, or architecture have been used. This repository neither modifies nor incorporates
the neighboring GPTKB source. Wikidata structured data are CC0; Wikipedia text retains its own
CC BY-SA attribution and source history. See [DATA_LICENSE.md](../DATA_LICENSE.md).
LLM outputs are hypotheses rather than truth; human review must distinguish evidential support from
universal factuality. Provider outputs and large caches are ignored by Git. Review artifacts before
public release. No repository has been published or pushed automatically.
