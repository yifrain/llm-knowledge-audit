from ..config import Config, LLMConfig
from ..disambiguation.string_baseline import normalize
from ..models import Candidate, Generation, Triple
from ..providers.base import Provider
from ..providers.client import CallClient
from .prompts import SYSTEM, VERSION


def deduplicate(triples: list[Triple]) -> tuple[list[Triple], int]:
    seen: set[tuple[str, ...]] = set()
    unique = []
    for triple in triples:
        key = (
            normalize(triple.subject),
            normalize(triple.predicate),
            normalize(triple.object),
            triple.object_type,
        )
        if key not in seen:
            unique.append(triple)
            seen.add(key)
    return unique, len(triples) - len(unique)


def generate(
    entity: Candidate, cfg: Config, client: CallClient, provider: Provider, model: LLMConfig
) -> tuple[list[Triple], int]:
    output = client.call(
        provider,
        model,
        "generate",
        VERSION,
        SYSTEM,
        {"entity": entity.model_dump(mode="json"), "count": cfg.triples_per_entity},
        Generation,
    )
    if len(output.triples) > cfg.triples_per_entity:
        raise ValueError("Generator exceeded requested triple count")
    if any(t.subject != entity.label for t in output.triples):
        raise ValueError("Generator changed the canonical subject")
    return deduplicate(output.triples)
