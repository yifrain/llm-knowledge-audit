import json

import pytest
from pydantic import ValidationError

from llm_knowledge_audit.config import Config
from llm_knowledge_audit.disambiguation.string_baseline import StringBaseline, normalize
from llm_knowledge_audit.evaluation.entity_metrics import rate
from llm_knowledge_audit.evaluation.judge_metrics import agreement
from llm_knowledge_audit.generation.generate_triples import deduplicate
from llm_knowledge_audit.judging.factuality_judge import judge
from llm_knowledge_audit.models import Generation, StringCandidate, Triple
from llm_knowledge_audit.providers.client import CallClient
from llm_knowledge_audit.providers.mock import MockProvider
from llm_knowledge_audit.storage import Cache, digest, write_new


def test_schema_rejects_invalid():
    with pytest.raises(ValidationError):
        Triple(subject="x", predicate="y", object="z", object_type="other")
    with pytest.raises(ValidationError):
        Generation.model_validate_json("not json")


def test_normalization():
    assert normalize(" Ｐｙｔｈｏｎ! Straße  ") == "python strasse"
    assert normalize("北京") == "北京"


def test_alias_ranking_and_abstention():
    candidates = [StringCandidate(entity_id="Q1", label="Other", aliases=["The Answer"])]
    assert StringBaseline().resolve("the answer", candidates).selected_entity_id == "Q1"
    assert StringBaseline().resolve("unknown", candidates).selected_entity_id is None
    assert StringBaseline().resolve("???", candidates).selected_entity_id is None


def test_duplicate_triples():
    triple = Triple(subject="A", predicate="B", object="C", object_type="literal")
    assert deduplicate([triple, triple]) == ([triple], 1)


def test_missing_evidence_never_calls_model(tmp_path):
    cfg = Config(cache_dir=tmp_path)
    client = CallClient(cfg)
    triple = Triple(subject="A", predicate="B", object="C", object_type="literal")
    output, supplied = judge(triple, [], client, MockProvider(), cfg.judge, 1000)
    assert output.label == "not_enough_information"
    assert supplied == client.events == []


def test_metrics_known_values():
    result = agreement(
        ["entailed", "contradicted", "not_enough_information"],
        ["entailed", "entailed", "not_enough_information"],
    )
    assert result["accuracy"]["value"] == pytest.approx(2 / 3)
    assert result["cohens_kappa"]["value"] == pytest.approx(0.5)
    assert result["macro_f1"]["value"] == pytest.approx(5 / 9)
    assert agreement([], [])["accuracy"]["value"] is None
    assert rate(0, 0)["value"] is None
    assert 0 < rate(5, 10, True)["wilson_95"][0] < 0.5


def test_cache_immutable(tmp_path):
    cache = Cache(tmp_path)
    key = digest({"a": 1})
    cache.put(key, {"value": 1})
    cache.put(key, {"value": 2})
    assert cache.get(key) == {"value": 1}
    with pytest.raises(FileExistsError):
        write_new(tmp_path / f"{key}.json", {})


def test_deterministic_mock():
    payload = {"entity": {"label": "Synthetic"}, "count": 5}
    first = MockProvider().complete("generate", "", payload, {})
    second = MockProvider().complete("generate", "", payload, {})
    assert first == second
    assert len(json.loads(first.content)["triples"]) == 5
