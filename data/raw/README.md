# Raw responses (private local artifacts)

Official public API response envelopes are in `http/`. LLM raw responses, including schema failures,
are in `llm/` and are never committed automatically. Content-addressed processed caches live in
`data/cache/`. Neither contains credentials; both can contain provider-generated text requiring review.
No raw text is treated as an instruction to this project. Public summaries needed for the benchmark
are explicitly version controlled outside this directory. Raw caches can be regenerated with the
collection scripts; do not replace frozen benchmark data during an experiment.
