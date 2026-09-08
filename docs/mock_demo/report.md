# Run report: MOCK / SYNTHETIC — not research findings

Run: `20260908T205131-ed0628aa8d44`

## Entity resolution

| Method | Correct / cases | Accuracy |
|---|---:|---:|
| string | 29 / 40 | 0.725 |
| context | 36 / 40 | 0.900 |

## Human evaluation

Reviewed annotations: 0 / 145 triples.
Missing human evaluation is unavailable, never inferred from model or fixture labels.

## Error analysis

Automatic flags are review leads; they do not establish causal explanations.

### same_label_wrong_sense

Status: automatically_flagged_for_review; flags: 11.

```json
{
  "case_id": "homonym_002",
  "method": "string",
  "predicted": "Q308",
  "gold": "Q925"
}
```

```json
{
  "case_id": "homonym_004",
  "method": "string",
  "predicted": "Q251",
  "gold": "Q3757"
}
```

```json
{
  "case_id": "homonym_005",
  "method": "string",
  "predicted": "Q89",
  "gold": "Q312"
}
```

### synonyms_not_merged

Status: automatically_flagged_for_review; flags: 2.

```json
{
  "case_ids": [
    "synonym_037",
    "synonym_038"
  ],
  "method": "string",
  "predictions": [
    null,
    "Q283"
  ]
}
```

```json
{
  "case_ids": [
    "synonym_033",
    "synonym_034"
  ],
  "method": "context",
  "predictions": [
    null,
    null
  ]
}
```

### distinct_entities_merged

Status: automatically_flagged_for_review; flags: 11.

```json
{
  "case_ids": [
    "homonym_001",
    "homonym_002"
  ],
  "method": "string",
  "predictions": [
    "Q308",
    "Q308"
  ]
}
```

```json
{
  "case_ids": [
    "homonym_003",
    "homonym_004"
  ],
  "method": "string",
  "predictions": [
    "Q251",
    "Q251"
  ]
}
```

```json
{
  "case_ids": [
    "homonym_005",
    "homonym_006"
  ],
  "method": "string",
  "predictions": [
    "Q89",
    "Q89"
  ]
}
```

### candidate_retrieval_failure

Status: requires_human_error_review; flags: 0.

### insufficient_context

Status: requires_human_error_review; flags: 0.

### generic_description

Status: requires_human_error_review; flags: 0.

### hallucinated_relation

Status: requires_human_error_review; flags: 0.

### temporal_mismatch

Status: requires_human_error_review; flags: 0.

### evidence_retrieval_failure

Status: requires_human_error_review; flags: 0.

### judge_false_positive

Status: requires_human_error_review; flags: 0.

### judge_false_negative

Status: requires_human_error_review; flags: 0.

### judge_overuse_nei

Status: requires_human_error_review; flags: 0.

### invalid_structured_output

Status: requires_human_error_review; flags: 0.

## Full metrics

All denominators and evidence-linked disagreements are in [evaluate.json](evaluate.json). Costs describe this invocation; reused artifacts retain their original provenance in the parent run.

## Limitations

Human review is required before claiming benchmark validity. Mock accuracy and zero mock latency/cost do not predict real LLM performance. Pair observations are dependent; Wilson case intervals are descriptive only. No empirical plots are produced from mock results.
