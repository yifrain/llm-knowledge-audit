> **Scope update (2026-09-11):** the current owner-focused path is a zero-annotation demo,
> five human-verified pilot cases, an optional twelve-case comparison, and **at most 20 initial
> generated-triple reviews**. The original 30–50/40-case and 100+-label targets below are optional
> extended-study goals, not current prerequisites. Use [the Chinese guide](../README_CN.md) first.

# Limitations and open work

- No completed human verification or human annotation. No paid LLM experiment. The scientific MVP
  cannot be described as complete, and current mock scores cannot support RQ1–RQ5 findings.
- Forty convenience cases span nine uneven domains and only English. Selection, knowledge prominence,
  short explicit contexts, and source-triple redundancy may favor context linking.
- Wikidata is used as an external target inventory; GPTKB's internal entity/relation/class
  canonicalization is a different problem. Objects and relation vocabularies are not canonicalized here.
- Live search rankings can miss the intended entity. Candidate recall limits resolution accuracy.
  Public metadata snapshots and raw caches are retained; mock pools include intended senses by design.
- The 113 collected claims are KB-derived practice material. Evidence from the same assertion is not
  independent truth verification and cannot establish factuality of generated LLM knowledge.
- Wikipedia-only English evidence has coverage and source bias. Missing pages, outdated text, neglected
  qualifiers, and time-sensitive facts can produce NEI. Claim-specific retrieval uses lexical overlap,
  not semantic retrieval or a truth oracle. Raw KB qualifiers are retained for practice claims but
  claims with qualifiers are excluded from that simplified cohort.
- Conflict handling is an instruction and tested mock behavior, not a separate semantic adjudicator.
  Evidence text can contain prompt injection; instructions treat it as untrusted, without guaranteeing
  that a real model will follow them.
- The proposed generator and judge are different snapshots within one vendor/model family; shared
  bias and self-preference remain possible. A second-family judge is future work.
- Temperature zero and a pinned model reduce variation but do not guarantee deterministic vendor
  inference. Optional seed transmission is disabled for the pilot. The mock is deterministic only.
- API schema/transport safeguards are tested with HTTP fixtures. Paid-provider compatibility and
  availability remain to be verified during the explicitly approved pilot.
- Confidence scores are uncalibrated. Group dependencies undermine naive interval interpretation;
  no statistical significance is claimed. Factual recall against exhaustive world facts is not estimated.
- Run directories are immutable after a stage finishes, but files are not cryptographically signed.
  Concurrent paid runs can duplicate requests; use a single process. Costs use configured published
  prices plus conservative reservations, not a billing API. An abrupt process kill may leave a paid
  response uncached; its pre-request reservation survives and counts against the resume budget.
- Raw invalid model responses may be private and are Git-ignored. Public artifacts should be reviewed
  before publication. No automatic publication, database, frontend, recursive crawl or private code reuse.

Next: review the five pilot cases, approve the priced pilot, inspect failures, freeze the full reviewed
benchmark, annotate at least 100 actual generated triples, and then produce measured figures and CV bullets.
