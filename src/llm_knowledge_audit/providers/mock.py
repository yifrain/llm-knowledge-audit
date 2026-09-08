"""Synthetic behavior, not an LLM and not a source of real-world facts."""

import json
from typing import Any

from ..disambiguation.string_baseline import normalize
from .base import Response


class MockProvider:
    def complete(
        self, task: str, system: str, payload: dict[str, Any], schema: dict[str, Any]
    ) -> Response:
        result: dict[str, Any]
        if task == "resolve":
            words = set(normalize(payload["context"]).split())
            ranked = sorted(
                payload["candidates"],
                key=lambda c: (
                    -len(words & set(normalize(c["description"]).split())),
                    c["entity_id"],
                ),
            )
            selected = ranked[0] if ranked else None
            supported = selected and words & set(normalize(selected["description"]).split())
            result = {
                "selected_entity_id": selected["entity_id"]
                if supported and selected is not None
                else None,
                "confidence": 0.8 if supported else 0.0,
                "short_rationale": "Synthetic lexical-overlap decision; not model reasoning.",
            }
        elif task == "generate":
            pairs = [
                ("demo_value", "alpha"),
                ("demo_value", "beta"),
                ("demo_unknown", "gamma"),
                ("demo_flag", "on"),
                ("demo_class", "sample"),
            ]
            result = {
                "triples": [
                    {
                        "subject": payload["entity"]["label"],
                        "predicate": rel,
                        "object": obj,
                        "object_type": "literal",
                    }
                    for rel, obj in pairs[: payload["count"]]
                ]
            }
        elif task == "judge":
            triple = payload["triple"]
            votes: dict[str, list[str]] = {"entailed": [], "contradicted": []}
            for passage in payload["evidence"]:
                try:
                    fact = json.loads(passage["text"])
                except (ValueError, TypeError):
                    continue
                if (
                    fact.get("subject") == triple["subject"]
                    and fact.get("predicate") == triple["predicate"]
                ):
                    label = "entailed" if fact.get("object") == triple["object"] else "contradicted"
                    votes[label].append(passage["passage_id"])
            nonempty = [label for label, ids in votes.items() if ids]
            label = nonempty[0] if len(nonempty) == 1 else "not_enough_information"
            result = {
                "label": label,
                "confidence": 0.8,
                "evidence_ids": votes.get(label, []),
                "short_rationale": "Synthetic fixture comparison only.",
            }
        else:
            raise ValueError(f"Unknown mock task: {task}")
        return Response(json.dumps(result))
