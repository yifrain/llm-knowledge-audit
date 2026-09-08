"""Resolve Wikipedia via canonical Wikidata sitelinks; retrieve official API extracts."""

import re
from urllib.parse import quote

from ..models import Evidence, Triple
from ..storage import digest
from .wikidata import Wikidata


class WikipediaRetriever:
    def __init__(self, wikidata: Wikidata):
        self.wikidata = wikidata

    def retrieve(self, entity_id: str, triple: Triple) -> list[Evidence]:
        record = self.wikidata.entities([entity_id])
        entity = record["data"]["entities"].get(entity_id, {})
        title = entity.get("sitelinks", {}).get("enwiki", {}).get("title")
        if not title:
            return []
        response = self.wikidata.http.get(
            "https://en.wikipedia.org/w/api.php",
            {
                "action": "query",
                "prop": "extracts|revisions",
                "explaintext": 1,
                "exsectionformat": "plain",
                "rvprop": "ids|timestamp",
                "titles": title,
                "redirects": 1,
                "format": "json",
                "formatversion": 2,
                "maxlag": 5,
            },
        )
        result: list[Evidence] = []
        query_words = set(re.findall(r"\w+", (triple.predicate + " " + triple.object).casefold()))
        for page in response["data"].get("query", {}).get("pages", []):
            revision = str(page.get("revisions", [{}])[0].get("revid", "unknown"))
            paragraphs = [s.strip() for s in page.get("extract", "").split("\n") if s.strip()]
            passages = []
            for index, text in enumerate(paragraphs):
                # Keep bounded complete paragraph passages, and provenance to article revision.
                if len(text) > 6000:
                    continue
                passage = Evidence.model_validate(
                    {
                        "passage_id": "wp-" + digest([entity_id, revision, index, text])[:20],
                        "text": text,
                        "source_url": f"https://en.wikipedia.org/w/index.php?title={quote(title)}&oldid={revision}",
                        "retrieved_at": response["retrieved_at"],
                        "revision_id": revision,
                        "license": "CC-BY-SA-4.0; Wikipedia contributors; see source history",
                        "synthetic": False,
                    }
                )
                score = len(query_words & set(re.findall(r"\w+", text.casefold())))
                passages.append((score, index, passage))
            passages.sort(key=lambda item: (-item[0], item[1]))
            result.extend(passage for _, _, passage in passages[:8])
        return result
