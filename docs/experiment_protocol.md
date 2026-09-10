> **Scope update (2026-09-11):** the current owner-focused path is a zero-annotation demo,
> five human-verified pilot cases, an optional twelve-case comparison, and **at most 20 initial
> generated-triple reviews**. The original 30–50/40-case and 100+-label targets below are optional
> extended-study goals, not current prerequisites. Use [the Chinese guide](../README_CN.md) first.

# Frozen experiment protocol

## Preconditions and data freeze

Human-review every included QID against its authoritative source and the intended sense. Fill
`verification_status=human_verified`, `verified_by`, and `verified_at` only after actual review.
For the pilot, edit `pilot_cases.jsonl`; transfer reviewed decisions to the corresponding full dataset
records with a documented change. Do not silently claim that pilot review validated all 40 records.
Version data changes and run the validator. Keep ambiguity groups together if introducing a dev/test
split. The current 40-case dataset has no held-out split; it is a descriptive pilot benchmark.

Freeze code, configuration, prompts, thresholds, candidates, and annotation protocol before the
full experiment. Candidate search receives only the mention and k. Both methods share these results.
No manual gold insertion or case-specific ranking. The controlled mock pools are not real retrieval.

## Execution

Start with `configs/mock.yaml`, then inspect `llmka pilot-plan`. The proposed real pilot is five cases
with 5 triples per selected seed, at most two selected QIDs per case, and at most 65 logical calls.
No paid request without explicit approval. The initial cap is USD 2, including conservative per-attempt
reservations. The 195 HTTP-attempt cap permits at most three attempts per planned logical call.
Missing API usage is reported as unknown with a conservative cost estimate. Do not infer billing
precision from estimates. Larger runs require a new approved budget, at most USD 10.

Generate triples once per unioned selected QID; save links to all methods and cases. Candidate metadata,
not gold descriptions, specifies the generator's entity. Do not generate from abstained cases.
Audit each unique subject/triple once. Record both per-method canonical-triple proportions and joint
correct-link-plus-entailed rates over mention/triple links. Report resolved-case coverage separately:
abstentions have no generated triples and must not disappear from entity accuracy denominators.

## Human evaluation

Sample at least 100 **LLM-generated** triples after the run, preferably all if manageable. Publish
sampling seed and selected IDs. If stratifying on judge label for rare labels, preserve sampling
probabilities and distinguish balanced diagnostic metrics from population-weighted estimates.
Use the run's blinded packet with the exact supplied evidence. Reviewers must not inspect judge
outputs until labels are frozen. Ideally double-annotate 20–30% and adjudicate disagreements;
one annotator is a stated limitation, not an agreement study between humans.

The 113 public Wikidata claims are a separate practice packet. Their evidence derives directly from
KB assertions; they have selection/circularity bias and must not substitute for generated triples.
A recorded human label needs identity, timestamp, evidence IDs, notes, and snapshot hashes.

## Resume and artifact integrity

A stage writes a file only once. `--resume` creates a new child run and copies successful checkpoints.
Evaluation/reporting always refresh so new annotation labels can be used. Other input/code/config
changes reject resume. A new fresh run may reuse content-addressed caches. Successful calls do not
re-bill on replay. Raw invalid responses are retained separately, without secrets, and not treated as
valid cached decisions. Interrupted requests may already have been billed: reservations are written
before transport and carried across the resume lineage. Reusing the same cache concurrently is safe
for writes but does not guarantee single-flight paid requests: run one paid process at a time.

A started run is not complete until `completion.json` exists. `completed_with_failures` differs from
successful completion. Inspect failure counts and prediction coverage. Source, data, and annotation
hashes are recorded. Git commit is null until this independent repository has a commit.

## Reporting

Report sample sizes, denominators, failures, abstentions, per-domain errors and all three judgment
labels. No significance claim from mock data. Confidence intervals on dependent observations are
only descriptive; preregister a group bootstrap before any inferential comparison. Do not present
missing annotations as zero agreement. Causal error categories require inspection; automatic flags
are not proof of hallucinations. Record retrieval date and temporal qualifiers where relevant.
