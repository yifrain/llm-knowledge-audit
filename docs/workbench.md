# Local research console

The console runs on `127.0.0.1:8765` (`llmka ui --open-browser`). Use `--port` for a second
instance. Restart an older server after updating Python code; refresh alone only reloads assets.
English is the default; the header language setting persists locally. Source evidence and triples
remain English and carry `lang="en"` even when the surrounding interface is Chinese.

## Run workflow

1. **Runs → New run:** choose Real experiment (default) or Mock, pilot/starter, and the case limit.
   The human-verified gold requirement is an explicit, unchecked option. Disabling it does not
   mark any gold verified: the immutable case snapshot and displayed coverage retain the truth.
2. **Cost & limits:** set a budget (up to the existing $10 configuration ceiling), API attempt
   cap and triples per entity. The call bound is the CLI `pilot-plan` formula
   `n + 2*n*(1 + triples_per_entity)`. It is a structural upper bound, not a live price quote.
   Retries consume additional attempts; public retrieval calls are separate. Mock has no charges.
3. **Models:** configure resolver, generator and judge independently. Verify the displayed
   price estimates yourself. The existing adapter requires HTTPS Chat Completions and strict
   JSON Schema. This change does not add or validate new provider protocols.
4. **Credentials:** enter per-role keys, or retain credentials already available in the process.
   Keys already loaded from the project `.env` at server start are displayed, but never used
   silently: each run requires explicit confirmation in the page ("Use keys from the project
   .env"), and entering keys manually counts as the same confirmation. A fresh preview always
   starts unconfirmed. Keys go to dedicated `LLMKA_WEB_<ROLE>_KEY` environment variables, never
   into Config, plans, manifests, job files, browser storage, or any API response. Password fields
   clear after submission. Clear keys using the credential step or stop the server. Credentials
   cannot change during an active run.
5. **Approval:** inspect models, endpoints, scope and caps; explicitly approve paid calls, then
   launch. The same `Pipeline(..., approved=True)` flag used by the CLI records `paid_approved`
   in the new manifest. Opening the console, previewing, or confirming gold grants no approval.
6. **Inspect:** stage artifacts determine the eight-stage progress display. Reservations show
   cumulative API attempts and reserved USD, including inherited reservations on resume.
   A reservation is a conservative ceiling reservation, not the provider's final invoice.

One worker runs at a time per server. Refreshing/closing the browser does not stop the worker.
Stopping the server does stop it; an unfinished run without a worker in the current server is
shown as failed/interrupted. Check for a still-running original process before resuming an
externally launched CLI run. Partial CLI invocations can be completed with fewer than eight stages.

**Resume in a new run** loads the original manifest configuration, previews inherited limits,
asks for credentials/approval again, and delegates signature validation to Pipeline. Changed code,
configuration or input data rejects resume. The parent directory is never overwritten. Jobs that
fail before a manifest exists remain visible as job records with a stable failure identifier.

## Human work and blind review

**Review → Gold entities** lists all selected-scope cases with context, gold description and cited
source. Select all or a subset, override individual QIDs/labels/descriptions/source URLs when
needed, supply a reviewer and confirm. Every batch has an explicit `batch_confirmation` event;
per-record history links to its batch ID. Matching pilot/starter records share confirmation.
No automatic review, fictitious reviewer or fabricated per-case decision is created.

**Review → Facts** is optional, exploratory and does not block the pipeline. It uses the original
seed-42 uniform sample of at most 20 generated triples. Labels are blank until the user submits
one; timestamps, evidence/triple hashes and edit history are automatic. Saved existing labels
can be edited. Evidence may be copied for translation. Do not substitute model labels for human
judgments. An incomplete sample cannot establish general judge reliability.

The blind gate is enforced by the backend, across all console access paths:

- Before **all sampled records** have valid, snapshot-bound annotations, overview metrics allow
  only entity/candidate/generation/operational fields. Factuality, joint scores, error flags,
  disagreements and judge-agreement fields are excluded. Trace returns no fact judgment.
- Review packets never contain model labels, confidence or rationale.
- Original reports, full metrics, figures and review comparisons remain locked until that gate
  opens. Completing the run never opens it. A zero-triple completed packet has no labels to hide.
- Blind-safe console summaries, manifest, cases, and review packet remain exportable. Optional
  annotation therefore does not block execution, entity metrics or those exports.

This is a console visibility gate, not filesystem access control. Opening raw `results/` artifacts
outside the console can compromise blinding; do not do that before completing a blind sample.

## Artifacts and boundaries

| Location | Contents |
|---|---|
| `results/<mode>/<run-id>/` | Existing immutable pipeline outputs; new runs only |
| `data/reviews/jobs/<job-id>/` | Exclusive-create queued, started and finished control records; no keys |
| `data/reviews/entity_history/` | Batch/individual review events and before/after records |
| `data/benchmark/{pilot,starter}_cases.jsonl` | Editable gold verification and explicit corrections |
| `data/reviews/real/<run-id>/human_annotations.jsonl` | Editable current human labels; revisions in `history/` |

Original report/figure exports reflect the original evaluation snapshot. Later UI annotations
are exported separately as `review-comparison.json`; they never silently replace original metrics.
Figure ZIPs are generated using the existing plot function in a disposable temporary directory,
then downloaded without adding or replacing anything in the run directory. Mock empirical
figures remain disabled. Source text may be English in the Chinese UI by design.

`runs.py` handles allowlisted configs, memory credentials, previews, worker state and progress;
`service.py` handles review and artifact views; `server.py` enforces loopback/same-origin/token/
body-size/static-asset restrictions. `i18n.js` holds paired message catalogs; `app.js` is vanilla
JS; no build step, CDN, remote fonts, frontend package dependencies or algorithm changes.

Backend errors use stable codes such as `approval_required`, `gold_required`, `resume_changed`,
`review_stale`, and `blind_locked`. Raw exceptions and validation payloads are not sent to clients
or persisted by the controller. Failure type and failed stage/item IDs support diagnosis without
storing a provider response body or credential-bearing exception text.

## Verification

`pytest` retains `--disable-socket`. Integration tests use temporary data copies and synthetic
providers to exercise real-mode orchestration without any network or paid experiment. They cover
approval and credential gates, no secret persistence, immutable resume, signature rejection,
failed/in-progress visibility, batch audit provenance, and every blind export gate. A fake HTTP
handler tests Host/Origin/token/CSP/whitelist rules without opening a socket.

`node tests/frontend/smoke.cjs` uses only Node built-ins to check the default English rendering,
message parity, language/title switching and data language marking. Pytest invokes it when Node
is installed; otherwise that one frontend test is skipped. Python runtime/UI do not require Node.
