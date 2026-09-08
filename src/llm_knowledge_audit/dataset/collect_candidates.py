"""Public candidate snapshot writer; deliberately has no gold-enrichment behavior."""

from pathlib import Path

from ..config import Config
from ..retrieval.wikidata import Wikidata
from ..storage import write_new
from .validate_cases import load_cases


def collect(cfg: Config, output: Path) -> None:
    source = Wikidata(cfg)
    cases = load_cases(cfg.dataset)
    snapshots = {}
    for surface in sorted({c.surface_form for c in cases}):
        snapshots[surface] = [
            c.model_dump(mode="json") for c in source.search(surface, cfg.candidate_k)
        ]
    write_new(output, snapshots)
