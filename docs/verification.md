# Local workbench and reduced-scope update (2026-09-11)

- 47 tests passed with sockets disabled, including 11 new workbench cases.
- Strict type checking passed for 43 Python source files; lint passed.
- The UI was opened in the local browser: flow, comparison, review guidance and mock-only behavior checked.
- The five-case and twelve-case datasets still have zero human confirmations; tests use temporary data only.
- A 12-case offline run completed. No model API calls or publication.
- Existing Chinese code comments were preserved; the earlier translated README is archived.
- Current scope and learning path: README_CN.md. Original 100+-label requirements are optional extensions.

## Earlier executed verification

- Fresh lockfile installation in a separate temporary Python 3.12 environment: passed.
- Python 3.12: 36 tests passed, with network sockets disabled by pytest-socket.
- `ruff check .`: passed.
- `mypy src`: passed (40 source files).
- `llmka validate-data --config configs/mock.yaml`: 40 valid draft records, zero human-verified.
- `llmka run-all --config configs/mock.yaml`: completed with no failures; 145 synthetic triples.
- Public Wikipedia smoke: 8 passages retrieved for Java (Q251), exact cached offline replay.
- Public data: 30 QID metadata records, 40 draft cases, ranked search snapshot, 113 blank claim annotations.
- No paid LLM call and no fabricated human annotation.

Tests cover normalization, schema validation, candidate ranking, abstention, unknown IDs,
malformed output, duplicates, missing/conflicting evidence, label parsing, unknown citations,
metric denominators, HTTP retries/cache/offline replay, refusals, approval/budget boundaries,
immutable resumes, interruption recovery, annotation refresh and blinded-packet consistency.

Python 3.11 is specified and included in CI; local execution so far used Python 3.12.
CI is configured but has not run on GitHub. Publication and research experiments are pending.
