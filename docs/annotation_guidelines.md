# Annotation guidelines

## Two distinct review tasks

**Entity review:** open the QID source for each case, verify label/aliases, intended sense and context,
check the source triple does not accidentally imply a different entity, then record reviewer/date.
Check synonym groups really share an entity and homonym pairs really differ. The supplied records
have only been checked automatically against public metadata. They are not human-verified gold.

**Triple review:** open a blinded annotation packet and the matching template. The public packet
contains 113 KB-derived practice claims; experiment packets contain generated claims. Never mix
these cohorts. For judge reliability, label only against the packet evidence, exactly as supplied to
the judge. Use source links to assess provenance; record any additional evidence separately and do
not introduce it into the paired comparison unless both the human and judge receive a new snapshot.

## Labels

- `entailed`: supplied evidence directly supports the entire proposition, including the correct entity,
  relation, object, scope, time and units. Paraphrases are acceptable.
- `contradicted`: supplied evidence establishes an incompatible proposition. A different value is
  contradictory only when the relation and time make the two values incompatible.
- `not_enough_information`: the claim cannot be settled from supplied evidence, including missing,
  partial, ambiguous, conflicting or unverifiable support.

An absent statement is not false. Multiple occupations, languages, spouses at different times, or
memberships can coexist. Do not infer single-valuedness merely from one returned KB statement.
NEI is an evidence sufficiency decision, not a claim that the fact is unknown to all people.

## Edge cases

**Partial support:** if only part of a compound claim is supported, choose NEI unless another part is
explicitly incompatible, in which case contradicted is appropriate; describe the unsupported portion.
Prefer atomic triples. **Temporal facts:** match dates/intervals; an old source does not support a
claim about the present. An explicitly incompatible claim for the same time is contradicted; absent
temporal alignment is NEI. **Numbers:** normalize exact unit conversions; accept rounding only at
the source's stated precision. Different measurement dates or methods may make a comparison NEI.
Do not invent a numeric tolerance after viewing a judge decision.

**Ambiguous entities:** verify the canonical QID; evidence about a namesake does not entail the claim.
If the packet never establishes identity, use NEI. **Conflicting sources:** first check dates, scope,
and corrections. If the supplied passages do not resolve the conflict, use NEI and cite both.
**Unverifiable claims:** subjective, vague, speculative and undocumented claims are usually NEI.
**KB-derived evidence:** a Wikidata assertion demonstrates what the KB says; inspect references and
avoid equating that assertion with independent real-world truth. These practice records are biased
toward support and cannot validate an LLM judge's real-world accuracy.

## Filling records

Keep `triple_id`, `triple_sha256`, and `evidence_sha256` unchanged. Set `human_label`, provide concise
`annotator_notes`, and cite packet passage IDs. Entailed/contradicted require citations. NEI can use
an empty list for missing evidence or cite partial/conflicting passages. Fill a real `annotator_id`
and UTC `annotated_at`. Null means **unreviewed**, never NEI. Do not copy the judge's rationale or
ask an LLM to impersonate a human reviewer. Do not claim inter-annotator reliability with one reviewer.

Place completed model-run records in the configured human annotation file and resume evaluation.
The evaluator rejects duplicate IDs, missing reviewer metadata and stale triple/evidence hashes.
Unmatched records are counted as out-of-run annotations and do not enter agreement denominators.
Preserve original files and any adjudication history.

## Error-review codes

After labels are frozen, inspect same-label wrong sense, synonyms not merged, distinct entities merged,
candidate misses, insufficient context, generic descriptions, hallucinated relations, temporal mismatches,
retrieval failures, false-positive/negative judge labels, excess NEI and malformed output. Automated
flags are leads. Add a concise justification referencing actual record IDs before making causal claims.
