> **Scope update (2026-09-11):** the current owner-focused path is a zero-annotation demo,
> five human-verified pilot cases, an optional twelve-case comparison, and **at most 20 initial
> generated-triple reviews**. The original 30–50/40-case and 100+-label targets below are optional
> extended-study goals, not current prerequisites. Use [the Chinese guide](../README_CN.md) first.

# Five-case pilot proposal · awaiting human review and explicit paid approval

No paid request has been made. This proposal is a small technical experiment, not a claim of results.

## Exact cases

| Case | Mention / intended sense | Proposed QID |
|---|---|---|
| homonym_001 | Mercury / planet | Q308 |
| homonym_002 | Mercury / element | Q925 |
| homonym_003 | Java / programming language | Q251 |
| synonym_023 | IBM / company | Q37156 |
| synonym_024 | International Business Machines / same company | Q37156 |

Review and fill human-verification fields in `data/benchmark/pilot_cases.jsonl` before execution.
The pilot file does not claim the other 35 cases have been reviewed.

## Provider, endpoint and prices

Provider: **OpenAI**, endpoint `https://api.openai.com/v1/chat/completions`.
Resolver and generator: **gpt-4.1-mini-2025-04-14**, USD 0.40 / million input tokens and
USD 1.60 / million output tokens. Judge: **gpt-4.1-2025-04-14**, USD 2.00 / million input and
USD 8.00 / million output tokens. Standard rates, no assumed prompt-cache or batch discounts.
Sources checked during preparation: [GPT-4.1 mini](https://developers.openai.com/api/docs/models/gpt-4.1-mini)
and [GPT-4.1](https://developers.openai.com/api/docs/models/gpt-4.1).
Model snapshots, supported structured outputs and account availability must be checked at execution.

## Planning estimate (assumptions, not measured usage)

The two methods can select at most 10 distinct seeds across five cases, though fewer are expected.
At five triples per seed the conservative workload estimate is:

| Task | Calls | Input tokens/call (assumed) | Output tokens/call (assumed) | Estimated USD |
|---|---:|---:|---:|---:|
| Context resolution | 5 | 2,000 | 200 | 0.0056 |
| Generation | 10 | 800 | 700 | 0.0144 |
| Judge | 50 | 2,200 | 180 | 0.2920 |
| Total | **65** | **128,000 total input** | **17,000 total output** | **0.3120** |

Round planning cost to **USD 0.32** before retries. At most 195 HTTP attempts (three per logical call),
subject to the **USD 2 conservative reservation cap**, which can stop execution early. The code reserves
input UTF-8 bytes plus a 4,096-token overhead and configured output caps before each request. That
reservation is intentionally more conservative than the planning estimate. Explicit approval covers
only this five-case configuration and USD 2; larger experiments need renewed approval.

No key is requested in chat. Set `LLMKA_API_KEY` locally. The implementation does not read it until
the approved provider request. Keep YAML key-free and never publish raw provider responses blindly.

## Execution after prerequisites

```bash
llmka validate-data --config configs/pilot.yaml
llmka pilot-plan --config configs/pilot.yaml
llmka run-all --config configs/pilot.yaml --approve-paid
```

Output: a fresh `results/real/<run-id>/` with manifest, candidates, both resolutions, generated triples,
evidence snapshots, judgments, metrics, failure telemetry, blinded annotation packet and report.
The pilot will produce at most 50 triples, so it cannot satisfy the later 100-triple human study.
No judge-agreement result exists until actual annotations are supplied. Inspect output validity,
retrieval coverage, grounded citations and identity errors before proposing the larger study.
