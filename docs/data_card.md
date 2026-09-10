> **Scope update (2026-09-11):** the current owner-focused path is a zero-annotation demo,
> five human-verified pilot cases, an optional twelve-case comparison, and **at most 20 initial
> generated-triple reviews**. The original 30–50/40-case and 100+-label targets below are optional
> extended-study goals, not current prerequisites. Use [the Chinese guide](../README_CN.md) first.

# Data card · draft-v1

Owner: Yifan Li. Language: English. Intended use: small, descriptive entity-linking and evidence-audit
experiments. Not a representative sample of world knowledge, not a knowledge-base replacement.

## Composition and review status

40 proposed cases; 20 homonym cases in 10 pairs, 20 synonym cases in 10 pairs; 30 distinct QIDs.
Domains: places 12, organizations 7, people 5, science 4, creative works 4, products 2, programming 2,
animals 2, history 2. Mythological Phoenix is grouped with creative works; apple fruit is grouped with
products. These coarse categories need reviewer confirmation. No claim of domain balance.
All 40 records have `pending_human_review`; none was labeled as human verified by the agent.

Source QIDs/labels/descriptions/aliases were checked against live official Wikidata API responses.
Contexts were independently written using familiar identifying relations, not copied from employer
materials. They are hand-designed and often easier than unconstrained generated mentions. The
`describedInContext` source-triple relation is a carrier for the context, not a separately verified
world fact. Context and source triple are redundant in this draft; no ablation isolates their effects.

Public search retains ranked API candidates (k=10); no gold insertion. The saved snapshot contains
38/40 proposed gold targets, with provisional misses for `homonym_008` (Michael Jordan) and
`homonym_018` (mythical phoenix). Human review may revise these targets. Snapshot provenance appears
per candidate; raw HTTP envelopes are cached privately. Search results can drift over time.

## Files

- `entity_cases.jsonl`: version-controlled proposed targets with pending human review.
- `pilot_cases.jsonl`: five-case subset, with its own explicit review state.
- `public_entity_metadata.json`: public API labels, aliases, descriptions, collection timestamp.
- `public_candidate_snapshot.json`: real ranked retrieval output, separate from gold cases.
- `tests/fixtures/candidates.json`: controlled metadata-backed mock candidate pools, not retrieval results.
- `collected_triples.jsonl` / `collected_evidence.jsonl`: 113 selected public KB claims and evidence.
- `human_annotations.template.jsonl`: 113 blank public-claim records with evidence/triple hashes.
- `human_annotations.jsonl`: empty; no human annotations fabricated.

The public review packet samples up to four distinct allowed properties per entity, skipping deprecated
claims, qualifiers, and time precision below year. Some entities have fewer than four eligible claims.
Selection is deterministic by property order; it is not random. It contains KB assertions, not LLM
outputs, and is support-biased. Generation-run templates are separate and must replace this practice
cohort for a real judge-reliability experiment.

## Provenance and licensing

Every collected passage retains URL, retrieval timestamp, revision and stable passage identifier.
Structured Wikidata data are CC0. Wikipedia extracts carry CC BY-SA attribution and revision history.
The neighboring GPTKB code/data and all proprietary employer materials are excluded. Data processing
scripts are included; collection scripts use exclusive writes and refuse to replace frozen artifacts.
For a new version, collect into a fresh checkout/output location and review the diff.
