# Current review scope

Start with `pilot_cases.jsonl` (5 cases). `starter_cases.jsonl` is an optional 12-case paired study.
The local workbench writes reviewer identity and time after your explicit confirmation, and copies
that decision only to identical cases in the other small subset. It never edits the original 40-case
pool or old experiment artifacts. No need to review all 40 cases or the 113 practice claims now.

The reduced 12-case pool has 6 homonym cases (Mercury, Java, Paris pairs) and 6 synonym cases
(IBM, Einstein, water pairs). It is a convenience set for learning and exploratory comparison.
The five-case pilot is not balanced and is only a technical smoke test.

# Benchmark review queue

`entity_cases.jsonl` holds **40 proposed cases**, not completed gold annotations. Open each `source_url`,
check its QID and intended entity sense, context and group assignment, then set the human reviewer and
date fields. Run `llmka validate-data --config configs/default.yaml` after review. Never ask the pipeline
to fill human verification automatically. Until all selected records are reviewed, real configs fail.

`public_candidate_snapshot.json` contains ranked automatically retrieved candidates. It must remain
separate from manually controlled gold records. Do not add missing gold IDs to search results.
`public_entity_metadata.json` records source-check metadata. The controlled pools in `tests/fixtures`
are labeled mock-only and do not measure retrieval recall.

The five-case pilot subset is `pilot_cases.jsonl`; it has its own pending review state. Full benchmark
verification must be performed separately. Collection scripts refuse to overwrite existing outputs.
Run them in a fresh copy when preparing a new version, then review source and data diffs.

The 113 `collected_triples.jsonl` records are public KB claims, not model generations. Their statements,
source references and passages are in this folder; the blinded packet and blank annotation template
are in `data/annotations`. The packet is practice material and cannot be substituted for a human
study of at least 100 actual generated LLM claims.
