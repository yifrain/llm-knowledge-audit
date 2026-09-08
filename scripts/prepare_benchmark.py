"""Independently authored contexts + public metadata. NEVER marks human verification."""

import json
from pathlib import Path

from llm_knowledge_audit.config import Config
from llm_knowledge_audit.retrieval.wikidata import Wikidata
from llm_knowledge_audit.storage import write_jsonl_new, write_new

ROOT = Path(__file__).resolve().parents[1]
# QIDs were checked against returned API labels/descriptions; still awaiting human review.
HOMONYMS = [
    ("Mercury", "Q308", "science", "A space probe studies the innermost planet orbiting the Sun."),
    ("Mercury", "Q925", "science", "A laboratory stores the liquid metal with chemical symbol Hg."),
    ("Java", "Q251", "programming", "The application runs bytecode on a virtual machine."),
    ("Java", "Q3757", "places", "The traveller visits Jakarta on this Indonesian island."),
    ("Apple", "Q312", "organizations", "This company designs the iPhone and Mac computers."),
    ("Apple", "Q89", "products", "The orchard harvests this fruit for juice and cider."),
    ("Jordan", "Q810", "places", "Amman is the capital of this Middle Eastern country."),
    ("Jordan", "Q41421", "people", "The Chicago Bulls basketball star won six NBA championships."),
    ("Paris", "Q90", "places", "The Eiffel Tower is a landmark of this European capital."),
    ("Paris", "Q830149", "places", "This city serves as the seat of Lamar County in Texas."),
    ("Jaguar", "Q35694", "animals", "This spotted big cat hunts in forests of the Americas."),
    ("Jaguar", "Q30055", "organizations", "This British car manufacturer produced the E-Type."),
    (
        "Python",
        "Q28865",
        "programming",
        "Developers use pip to install packages for this language.",
    ),
    ("Python", "Q271218", "animals", "This snake genus includes the species Python regius."),
    ("Amazon", "Q3884", "organizations", "This company operates AWS and an online marketplace."),
    (
        "Amazon",
        "Q177567",
        "places",
        "This tropical rainforest covers a large area of South America.",
    ),
    ("Phoenix", "Q16556", "places", "The government of Arizona is based in this state capital."),
    ("Phoenix", "Q48444", "creative_works", "This mythical bird is reborn from its ashes."),
    (
        "Titanic",
        "Q44578",
        "creative_works",
        "James Cameron directed this film starring Kate Winslet.",
    ),
    (
        "Titanic",
        "Q25173",
        "products",
        "This passenger liner struck an iceberg during its 1912 voyage.",
    ),
]
SYNONYMS = [
    (
        "Q60",
        "places",
        ["NYC", "New York City"],
        "Manhattan is one of the five boroughs of this city.",
    ),
    (
        "Q37156",
        "organizations",
        ["IBM", "International Business Machines"],
        "This technology company developed the System/360 family of computers.",
    ),
    (
        "Q49108",
        "organizations",
        ["MIT", "Massachusetts Institute of Technology"],
        "This research university is located in Cambridge, Massachusetts.",
    ),
    ("Q30", "places", ["USA", "United States"], "Washington, D.C. is the capital of this country."),
    (
        "Q145",
        "places",
        ["UK", "United Kingdom"],
        "This country includes England, Scotland and Wales.",
    ),
    (
        "Q937",
        "people",
        ["Einstein", "Albert Einstein"],
        "This physicist developed general relativity.",
    ),
    ("Q892", "people", ["Tolkien", "J. R. R. Tolkien"], "This author wrote The Lord of the Rings."),
    (
        "Q74287",
        "creative_works",
        ["The Hobbit", "The Hobbit, or There and Back Again"],
        "This novel follows Bilbo Baggins on a journey with dwarves.",
    ),
    ("Q283", "science", ["H2O", "water"], "Each molecule of this compound has two hydrogen atoms."),
    ("Q362", "history", ["WWII", "Second World War"], "This global conflict ended in 1945."),
]


def main():
    cfg = Config(offline=False, cache_dir=ROOT / "data/cache", raw_dir=ROOT / "data/raw")
    source = Wikidata(cfg)
    ids = list(dict.fromkeys([r[1] for r in HOMONYMS] + [r[0] for r in SYNONYMS]))
    record = source.entities(ids)
    metadata = {
        q: source.candidate(q, e, record["retrieved_at"]).model_dump(mode="json")
        for q, e in record["data"]["entities"].items()
    }
    write_new(
        ROOT / "data/benchmark/public_entity_metadata.json",
        {
            "status": "automatically_source_checked_not_human_verified",
            "retrieved_at": record["retrieved_at"],
            "source_url": record["source_url"],
            "entities": metadata,
        },
    )
    cases = []

    def add(surface, qid, domain, context, kind, group):
        c = metadata[qid]
        cases.append(
            dict(
                case_id=f"{kind}_{len(cases) + 1:03}",
                case_type=kind,
                group_id=group,
                surface_form=surface,
                domain=domain,
                context=context,
                source_triple=dict(subject=surface, predicate="describedInContext", object=context),
                gold_entity_id=qid,
                gold_label=c["label"],
                gold_description=c["description"],
                source_url=c["source_url"],
                retrieved_at=c["retrieved_at"],
                verification_status="pending_human_review",
                verified_by=None,
                verified_at=None,
            )
        )

    for surface, qid, domain, context in HOMONYMS:
        add(surface, qid, domain, context, "homonym", surface.casefold())
    for qid, domain, surfaces, context in SYNONYMS:
        for surface in surfaces:
            add(surface, qid, domain, context, "synonym", qid)
    write_jsonl_new(ROOT / "data/benchmark/entity_cases.jsonl", cases)
    # Controlled fixture pool is explicitly not candidate-retrieval evidence.
    fixture = {}
    for c in cases:
        pool = [metadata[x["gold_entity_id"]] for x in cases if x["group_id"] == c["group_id"]]
        fixture[c["surface_form"]] = list({x["entity_id"]: x for x in pool}.values())
    # Metadata-backed fixture, used only in mock pipeline; includes no generated human labels.
    (ROOT / "tests/fixtures/candidates.json").write_text(
        json.dumps(fixture, indent=2, ensure_ascii=False)
    )
    print(f"Prepared {len(cases)} DRAFT cases, {len(metadata)} public entity records.", flush=True)
    search = {}
    for surface in sorted(fixture):
        search[surface] = [c.model_dump(mode="json") for c in source.search(surface, 10)]
        print("Collected", surface, len(search[surface]), flush=True)
    write_new(ROOT / "data/benchmark/public_candidate_snapshot.json", search)


if __name__ == "__main__":
    main()
