from __future__ import annotations

from typing import Any

from ..config import Config
from ..models import Candidate
from .http import PublicHTTP, RetrievalError

API = "https://www.wikidata.org/w/api.php"


class Wikidata:
    def __init__(self, cfg: Config):
        self.http = PublicHTTP(cfg)

    def entities(self, ids: list[str]) -> dict[str, Any]:
        return self.http.get(
            API,
            {
                "action": "wbgetentities",
                "ids": "|".join(ids),
                "props": "labels|aliases|descriptions|sitelinks",
                "languages": "en|mul",
                "languagefallback": 1,
                "format": "json",
                "maxlag": 5,
            },
        )

    @staticmethod
    def candidate(qid: str, entity: dict[str, Any], timestamp: str) -> Candidate:
        labels = entity.get("labels", {})
        label = labels.get("en", labels.get("mul", {})).get("value")
        if not label:
            raise RetrievalError(f"No English or multilingual label for {qid}")
        return Candidate.model_validate(
            {
                "entity_id": qid,
                "label": label,
                "aliases": [a["value"] for a in entity.get("aliases", {}).get("en", [])],
                "description": entity.get("descriptions", {}).get("en", {}).get("value", ""),
                "source_url": f"https://www.wikidata.org/wiki/{qid}",
                "retrieved_at": timestamp,
            }
        )

    def search(self, surface_form: str, k: int) -> list[Candidate]:
        search = self.http.get(
            API,
            {
                "action": "wbsearchentities",
                "search": surface_form,
                "language": "en",
                "uselang": "en",
                "type": "item",
                "limit": k,
                "format": "json",
                "maxlag": 5,
            },
        )
        ids = list(dict.fromkeys(c["id"] for c in search["data"].get("search", [])))
        if not ids:
            return []
        record = self.entities(ids)
        # Preserve API rank; never insert the gold entity or select using benchmark context.
        return [
            self.candidate(qid, record["data"]["entities"][qid], record["retrieved_at"])
            for qid in ids
            if "missing" not in record["data"]["entities"][qid]
        ]
