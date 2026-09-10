> **Scope update (2026-09-11):** the current owner-focused path is a zero-annotation demo,
> five human-verified pilot cases, an optional twelve-case comparison, and **at most 20 initial
> generated-triple reviews**. The original 30–50/40-case and 100+-label targets below are optional
> extended-study goals, not current prerequisites. Use [the Chinese guide](../README_CN.md) first.

# Research plan

## Objective

Study context-assisted linking of ambiguous entity mentions and the reliability of a retrieval-backed
factuality judge. This is a small convenience benchmark, not a population estimate of LLM knowledge.

## Ordered implementation milestones

1. Inspect existing files, preserve the existing GPTKB checkout, create independent packaging.
2. Verify a small mock pipeline with strict models, separate resolver inputs and immutable outputs.
3. Collect public candidates/metadata and author 40 draft cases; preserve raw responses and provenance.
4. Add generator, canonical retrieval, evidence-only judge, metrics, error flags and safeguards.
5. Validate offline execution, types, lint, transport fixtures and interrupted-run recovery.
6. Human-review the five pilot cases; explicitly approve the exact priced pilot.
7. Run the pilot, inspect raw structured outputs and retrieval coverage, then freeze changes.
8. Human-verify at least 30 cases and annotate at least 100 actual generated triples.
9. Run the frozen experiment, compute paired outcomes and human agreement, generate figures.
10. Write evidence-supported conclusions and three concise CV bullets only after real results exist.

Milestones 1–5 have been executed. Steps 6–10 depend on human work and/or paid-call approval.

## Design decisions

Use Python/Pydantic interfaces and plain files, without a database or recursive crawl. Keep automatic
candidates separate from human-controlled gold. Use the same candidate pool for both methods; do
not give the baseline descriptions or source triples. Share factual generation by canonical subject,
preserving every method/case link. Use complete evidence passages and blind human reviewers to judge
labels. Use distinct generator/judge snapshots, while acknowledging common model-family bias.

## Hypotheses (not findings)

H1: Context improves case-level linking accuracy, especially where surface forms are shared.
H2: Context reduces homonym conflation without reducing correct synonym merges.
H3: Judge agreement varies across labels and evidence coverage.
H4: Abstention improves conditional accuracy but can mask low coverage if coverage is omitted.

## Risks and assumptions

Draft cases were selected for recognizability and domain variety. Contexts were authored alongside
proposed targets, not randomly sampled from model outputs. They can be unusually informative.
No prompt tuning should use final evaluation labels. Candidate search order and descriptions can
change; use the saved snapshot. Annotator availability and explicit paid approval are open dependencies.
Abstention confidence is not calibrated. Wikipedia coverage limits factuality conclusions.
