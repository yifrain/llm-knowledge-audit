# Research console verification — 2026-09-13

- 63 tests passed with pytest-socket `--disable-socket` retained.
- Ruff passed; mypy passed for 44 source files.
- Dependency-free Node smoke passed: English default, language/title switch, catalog parity,
  and English data-region marking.
- New coverage: approval/credential preflight, no secret persistence, optional gold gate,
  background lifecycle, interrupted/failed records, immutable resume and signature rejection,
  batch-confirmation provenance, all-sample blind visibility/export gate, and HTTP protections.
- Browser checked: real wizard through credential entry (no real key entered), mock wizard through
  eight stages to results, language switch, batch source table, narrow layout and summary download.
- No paid model calls were made. Real-mode orchestration tests used synthetic providers/retrievers
  in temporary directories. No synthetic fixture is presented as a real experiment.
- Existing pipeline, judging and evaluation semantics were not changed by this refactor.

Earlier verification records follow.

---

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
