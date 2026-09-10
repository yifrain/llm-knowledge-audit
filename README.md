# Context-Aware Entity Disambiguation and Factuality Auditing for LLM-Generated Knowledge

**Yifan Li · M.Sc. Computer Science · TU Dresden**

A small, reproducible research prototype: compare string-only entity linking with context-guided
linking, then inspect the evidence behind factual claims about the selected entities.

**New here? Start with [the Chinese learning guide](README_CN.md).** It explains the terminology,
pipeline, code-reading order, exact review steps, provider choices, and interview talking points.
The code and research-facing documents remain primarily English.

## A manageable first experiment

The default learning path has been reduced at the owner's request. A complete large benchmark is
not a prerequisite for understanding the project or discussing it in an interview.

| Stage | Scope | Human effort |
|---|---|---|
| Learn | 12-case offline demonstration | No annotation |
| First real pilot | 5 cases | Verify those 5 entities; approve the provider/budget separately |
| Optional judge check | Fixed random sample of at most 20 generated triples | Review the supplied evidence and choose labels |
| Optional paired comparison | 12 cases: 6 homonym + 6 synonym | Review only the remaining cases |
| Future extended study | Original 40 cases and 100+ generated-triple annotations | Optional, not the current task |

Twenty labels support a small diagnostic check, **not a general reliability claim**. The 113 existing
public-KB practice claims do not need annotation and are not the model-generated evaluation set.
No human labels or verification decisions have been fabricated. No paid experiment has been executed.

## Open the local workbench

```bash
uv sync --frozen --extra dev --extra plots
source .venv/bin/activate
llmka ui --open-browser
```

On macOS, after installation you can also double-click `打开工作台.command`.
The workbench listens only at `http://127.0.0.1:8765`:

- **Understand the flow:** follow a single mention through candidates, both methods, generated
  triples, evidence and evaluation; Chinese explanations point to the relevant implementation.
- **Inspect results:** compare actual saved outputs with denominators and explicit mock/real labels.
- **Lightweight review:** verify five cases and, after a real run, annotate at most 20 randomly
  sampled claims without seeing judge labels. IDs, timestamps and evidence hashes are automatic.

There is no frontend build system, database, external asset dependency or paid-run button.
The UI wraps the same Python pipeline and metrics as the CLI. English source text stays intact;
Chinese context aids and a copy-for-translation action reduce reading burden.

## Run without a UI

```bash
llmka run-all --config configs/learn.yaml   # 12-case offline learning run
llmka run-all --config configs/mock.yaml    # optional original 40-case mock run
llmka pilot-plan --config configs/pilot.yaml
pytest
ruff check .
mypy src
```

Python 3.11+; exact dependencies are in `uv.lock`. Installation needs package access once, but
mock execution and tests need neither API credentials nor network access. Each run creates a new
immutable directory. Workbench reviews are saved separately under `data/reviews/`, never over old runs.

## Research question and boundaries

Does relational context help distinguish homonyms and merge synonymous mentions? Can an
 evidence-grounded judge produce defensible labels on a small independently reviewed subset?
The string baseline sees only labels and aliases. The context method also sees context/source-triple
information and candidate descriptions. Both use the same candidates and may abstain.
Generation uses the union of their actual selected entities, preserving links to the method/case.
Wikipedia passages are retrieved through canonical Wikidata sitelinks and an official API.

The project links **subjects** to an external KB. It does not train models, construct a large KB,
canonicalize all objects/relations/classes, or reproduce the full GPTKB system. Hand-designed contexts,
small convenience samples, uncalibrated confidence and limited evidence restrict the conclusions.

**GPT is not required by the study design.** Currently implemented providers are a deterministic
mock and an HTTPS Chat Completions adapter requiring strict JSON-schema support. Other providers
may work when their protocol matches; unsupported protocols/local servers need an adapter.
No universal compatibility or paid-live-tested support is claimed. Changing provider/model alone is
not enough unless the endpoint, output format, usage envelope and configured prices are compatible.
The [pilot proposal](docs/pilot_proposal.md) retains exact GPT snapshots as one proposed configuration;
no API call is authorized by opening the UI or verifying a case.

## What has actually been done?

The core pipeline, local UI, tests, public retrieval and report generation are implemented.
Saved [mock results](docs/mock_demo/report.md) are software checks, not LLM performance findings.
Public metadata and candidate searches exist for 40 proposed cases; 113 KB-derived claims are
available as optional practice material. Human verification and real LLM measurements remain pending.
The first paid pilot and any larger run require explicit approval. Human fact review is optional for
the initial linking demonstration; RQ4 judge reliability remains unmeasured if it is skipped.

## Read in order

1. [中文学习入口 / Start here](README_CN.md)
2. [中文代码导读 / Code walkthrough](docs/code_walkthrough.zh-CN.md)
3. When needed: [pilot proposal](docs/pilot_proposal.md), [metric definitions](docs/metrics.md),
   [annotation reference](docs/annotation_guidelines.md), [technical reference](docs/technical_reference.md).

The older detailed protocol and paper-style draft remain reference material; their expanded-study
requirements are not the current learning checklist. No need to read all documents first.

## Research context and licensing

Inspired by [Hu et al., ACL 2025](https://aclanthology.org/2025.acl-long.789/),
[GPTKB 2.0 construction](https://arxiv.org/abs/2608.03729v3),
[the GPTKB 2.0 auditing demo](https://arxiv.org/abs/2608.06992v2), and
[Giordano and Razniewski's open knowledge evaluation](https://arxiv.org/abs/2605.26937v2).
See [references.bib](docs/references.bib) for bibliographic entries.

Independently written MIT code; Wikidata structured data are CC0, and Wikipedia text retains its own
attribution and license. See [DATA_LICENSE.md](DATA_LICENSE.md). No proprietary employer material or
neighboring GPTKB source was incorporated. No paid calls or automatic publication.
