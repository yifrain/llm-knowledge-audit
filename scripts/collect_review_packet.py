"""Collect public KB claims for human-review practice, NOT LLM-generated evaluation."""

from pathlib import Path

from llm_knowledge_audit.config import Config
from llm_knowledge_audit.models import Annotation, Evidence, Triple
from llm_knowledge_audit.retrieval.http import PublicHTTP
from llm_knowledge_audit.storage import digest, read_json, write_jsonl_new, write_new

ROOT = Path(__file__).resolve().parents[1]
PROPERTIES = [
    "P31",
    "P17",
    "P30",
    "P279",
    "P361",
    "P131",
    "P495",
    "P50",
    "P57",
    "P178",
    "P112",
    "P19",
    "P20",
    "P569",
    "P570",
    "P571",
    "P577",
    "P36",
    "P37",
    "P105",
    "P171",
    "P225",
    "P61",
    "P138",
    "P123",
    "P641",
    "P106",
    "P800",
    "P27",
    "P1082",
    "P2048",
    "P2067",
    "P2076",
    "P2101",
]


def main():
    cfg = Config(offline=False, cache_dir=ROOT / "data/cache", raw_dir=ROOT / "data/raw")
    http = PublicHTTP(cfg)
    metadata = read_json(ROOT / "data/benchmark/public_entity_metadata.json")["entities"]
    response = http.get(
        "https://www.wikidata.org/w/api.php",
        {
            "action": "wbgetentities",
            "ids": "|".join(metadata),
            "props": "claims|info",
            "format": "json",
            "maxlag": 5,
        },
    )
    selected = []
    for qid, entity in response["data"]["entities"].items():
        count = 0
        for pid in PROPERTIES:
            for claim in entity.get("claims", {}).get(pid, []):
                snak = claim.get("mainsnak", {})
                if (
                    claim.get("rank") == "deprecated"
                    or claim.get("qualifiers")
                    or snak.get("snaktype") != "value"
                    or snak.get("datatype") not in {"wikibase-item", "time", "string", "quantity"}
                ):
                    continue
                value = snak.get("datavalue", {}).get("value")
                if isinstance(value, dict) and "time" in value and value.get("precision", 0) < 9:
                    continue
                selected.append((qid, pid, claim, entity.get("lastrevid")))
                count += 1
                break  # At most one claim per property, to broaden review topics.
            if count == 4:
                break
        print(qid, count, flush=True)
    ids = {pid for _, pid, _, _ in selected}
    for _, _, claim, _ in selected:
        val = claim["mainsnak"]["datavalue"]["value"]
        if isinstance(val, dict) and "id" in val:
            ids.add(val["id"])
    labels = {}
    ids = sorted(ids)
    for offset in range(0, len(ids), 50):
        r = http.get(
            "https://www.wikidata.org/w/api.php",
            {
                "action": "wbgetentities",
                "ids": "|".join(ids[offset : offset + 50]),
                "props": "labels",
                "languages": "en|mul",
                "languagefallback": 1,
                "format": "json",
                "maxlag": 5,
            },
        )
        for key, e in r["data"]["entities"].items():
            ll = e.get("labels", {})
            labels[key] = ll.get("en", ll.get("mul", {})).get("value", key)
    triples = []
    passages = []
    annotations = []
    packet = {}
    for qid, pid, claim, revision in selected:
        snak = claim["mainsnak"]
        value = snak["datavalue"]["value"]
        datatype = snak["datatype"]
        if datatype == "wikibase-item":
            obj = labels[value["id"]]
        elif datatype == "time":
            date = value["time"].lstrip("+").split("T")[0]
            obj = (
                date[:4]
                if value["precision"] == 9
                else date[:7]
                if value["precision"] == 10
                else date
            )
        elif datatype == "quantity":
            obj = value["amount"] + " (unit " + value["unit"] + ")"
        else:
            obj = str(value)
        triple = Triple(
            subject=metadata[qid]["label"],
            predicate=labels[pid],
            object=obj,
            object_type="entity" if datatype == "wikibase-item" else "literal",
        )
        tid = "public-" + digest([qid, claim["id"], triple.model_dump()])[:20]
        evidence = Evidence.model_validate(
            {
                "passage_id": "wd-" + digest([claim["id"], revision])[:20],
                "text": f"Wikidata statement: {triple.subject} ({qid}) — "
                f"{triple.predicate} ({pid}) — {obj}. "
                "This is a KB assertion; inspect the statement references before assessing truth.",
                "source_url": f"https://www.wikidata.org/w/index.php?title={qid}&oldid={revision}",
                "retrieved_at": response["retrieved_at"],
                "revision_id": str(revision),
                "license": "CC0-1.0 (Wikidata structured data)",
                "synthetic": False,
            }
        )
        ev = [evidence.model_dump(mode="json")]
        row = {
            "triple_id": tid,
            "entity_id": qid,
            "triple": triple.model_dump(),
            "origin": "public_wikidata_claim",
            "statement_id": claim["id"],
            "statement": claim,
            "evidence_ids": [evidence.passage_id],
        }
        triples.append(row)
        passages += ev
        annotations.append(
            Annotation(
                triple_id=tid, evidence_sha256=digest(ev), triple_sha256=digest(triple.model_dump())
            ).model_dump(mode="json")
        )
        packet[tid] = {
            "triple": triple.model_dump(),
            "entity_id": qid,
            "evidence": ev,
            "origin": "public_wikidata_claim_not_llm_generated",
        }
    write_jsonl_new(ROOT / "data/benchmark/collected_triples.jsonl", triples)
    write_jsonl_new(ROOT / "data/benchmark/collected_evidence.jsonl", passages)
    write_jsonl_new(ROOT / "data/annotations/human_annotations.template.jsonl", annotations)
    write_new(ROOT / "data/annotations/public_review_packet.json", packet)
    print("Collected", len(triples), "claims; all human labels remain null.", flush=True)


if __name__ == "__main__":
    main()
