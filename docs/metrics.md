# Metric definitions

All proportions carry numerator/denominator; zero-denominator values are null. Report counts next
to each metric, including missing predictions. Macro scores use the fixed three-label set.

| Metric | Numerator / denominator or definition |
|---|---|
| Recall@k | Cases whose gold QID is in first k candidates / all cases |
| MRR@k | Sum of reciprocal gold ranks, zero for misses / all cases |
| Top-1 | Correct selected QIDs / all cases (abstention/failure is incorrect) |
| Abstention | Null selections, including separately flagged failures / all cases |
| Conditional accuracy | Correct selections / non-null selections |
| Homonym separation | Both QIDs correct / distinct-gold pairs in each homonym group |
| Homonym conflation | Same non-null predicted QID / eligible homonym pairs |
| Synonym merge | Both mentions mapped to their shared correct QID / eligible synonym pairs |
| Per-domain errors | Incorrect or null case selections / cases in that domain |
| Output validity | Parse/schema-valid responses / uncached logical calls (including refusals) |
| Generation acceptance | Semantically valid generation outputs / attempted canonical seeds |
| Duplicate rate | Removed normalized duplicates / parsed triples before deduplication |
| Mean triples per seed | Kept triples / attempted canonical seeds, failures contribute zero |
| Label proportion | Count of each label / valid judgments |
| Strict factual precision | Entailed judgments / all attempted triples, including failures |
| Decisive factual precision | Entailed / (entailed + contradicted), excludes NEI and failures |
| Joint entity/fact success | Correct entity AND entailed / method-linked mention/triple pairs |
| Judge coverage | Valid predictions / annotated triples |
| Judge accuracy | Exact label matches / annotations with valid predictions |
| Failure-inclusive accuracy | Exact matches / all annotated triples |
| Macro P/R/F1 | Unweighted mean across three label-specific scores, zero for undefined scores when n>0 |
| Kappa | (observed agreement − chance agreement) / (1 − chance agreement) |

Confusion matrix rows are human labels; columns are judge labels. Kappa is null when n=0 or chance
agreement is 1. Label-specific precision denominators are prediction counts; recall denominators are
human supports. F1 carries human support and prediction count. Failures are not a fourth truth label;
report their coverage and failure-inclusive accuracy separately.

Homonym/synonym pair rates use pairs, not mentions. Two nulls never count as a successful merge or
separation. Two wrong identical synonym mappings are not successful merges. These pairs share
observations, so independence-based confidence intervals are not reported for pair metrics.

Wilson 95% intervals accompany eligible case/claim proportions. Because cases and triples cluster by
entity/group, these are descriptive and potentially overconfident, not inferential evidence. A paired
McNemar test or grouped bootstrap remains future work after the human-verified benchmark is frozen.

Operation metrics refer to new logical calls in the current invocation; cache hits are separate.
Latency is end-to-end logical-call time including retry waits. Percentiles use linear interpolation.
Token totals count returned API usage; unavailable usage is marked unknown. Transient attempts with
unknown usage contribute their conservative cost reservation. Reservations are upper estimates,
not charges. Public HTTP telemetry is separate from paid provider requests. Resume ancestry preserves
prior costs; a cached run's zero incremental cost is not the original experiment cost.

Generated unique canonical triples and method-linked mention/triple outcomes use different
population units and are reported separately. A method that abstains heavily can look precise on
its surviving triples; resolved-case coverage and full-case linking accuracy must accompany precision.
