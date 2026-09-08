import json
from datetime import UTC, datetime

import httpx
import pytest
from pydantic import ValidationError

from llm_knowledge_audit.config import Config, LLMConfig
from llm_knowledge_audit.disambiguation.context_guided import ContextGuided
from llm_knowledge_audit.evaluation.entity_metrics import candidate_metrics, entity_metrics
from llm_knowledge_audit.judging.factuality_judge import judge, prepare_evidence
from llm_knowledge_audit.models import (
    Annotation,
    Candidate,
    EntityCase,
    Evidence,
    Generation,
    Judgment,
    Resolution,
    SourceTriple,
    Triple,
)
from llm_knowledge_audit.providers.base import ExecutionBlocked, ProviderError, Response
from llm_knowledge_audit.providers.client import CallClient, TransientProviderError
from llm_knowledge_audit.providers.mock import MockProvider
from llm_knowledge_audit.providers.openai_compatible import OpenAICompatible
from llm_knowledge_audit.retrieval.http import PublicHTTP, RetrievalError


class Stub:
    def __init__(self, content):
        self.content = content
        self.calls = 0
        self.payloads = []

    def complete(self, task, system, payload, schema):
        self.calls += 1
        self.payloads.append(payload)
        return Response(self.content, 10, 5)


def evidence(text="some evidence", pid="p1"):
    return Evidence(
        passage_id=pid,
        text=text,
        source_url="https://example.org",
        retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
        license="test",
    )


def triple():
    return Triple(subject="Subject", predicate="relation", object="Object", object_type="literal")


def candidate():
    return Candidate(
        entity_id="Q1",
        label="Subject",
        description="description",
        source_url="https://www.wikidata.org/wiki/Q1",
    )


def test_context_rejects_unknown_ids_and_gold_not_in_payload(tmp_path):
    cfg = Config(cache_dir=tmp_path / "cache", raw_dir=tmp_path / "raw")
    provider = Stub(
        Resolution(selected_entity_id="Q999", confidence=0.9, short_rationale="x").model_dump_json()
    )
    resolver = ContextGuided(CallClient(cfg), provider, cfg.resolver, 0.6)
    with pytest.raises(ValueError, match="outside"):
        resolver.resolve(
            "Subject",
            "context",
            SourceTriple(subject="a", predicate="b", object="c"),
            [candidate()],
        )
    assert not any("gold" in key for key in provider.payloads[0])


def test_context_confidence_abstains(tmp_path):
    cfg = Config(cache_dir=tmp_path / "cache", raw_dir=tmp_path / "raw")
    provider = Stub(
        Resolution(selected_entity_id="Q1", confidence=0.2, short_rationale="x").model_dump_json()
    )
    resolver = ContextGuided(CallClient(cfg), provider, cfg.resolver, 0.6)
    output = resolver.resolve(
        "Subject", "context", SourceTriple(subject="a", predicate="b", object="c"), [candidate()]
    )
    assert output.selected_entity_id is None


@pytest.mark.parametrize("content", ["not json", "{}", '{"triples":[{"subject":"a"}]}'])
def test_bad_output_is_not_retried_or_accepted(tmp_path, content):
    cfg = Config(cache_dir=tmp_path / "cache", raw_dir=tmp_path / "raw")
    client = CallClient(cfg)
    provider = Stub(content)
    with pytest.raises(ValidationError):
        client.call(provider, cfg.generator, "generate", "v1", "", {}, Generation)
    assert provider.calls == 1
    assert client.events[0]["schema_valid"] is False
    assert not list((tmp_path / "cache").rglob("*.json"))
    assert list((tmp_path / "raw/llm").glob("*.json"))


@pytest.mark.parametrize("label", ["entailed", "contradicted", "not_enough_information"])
def test_label_parsing(label):
    assert (
        Judgment(label=label, confidence=0.9, evidence_ids=["p1"], short_rationale="x").label
        == label
    )


def test_judge_invalid_label():
    with pytest.raises(ValidationError):
        Judgment(label="true", confidence=0.9, evidence_ids=[], short_rationale="x")


def test_judge_unknown_citation(tmp_path):
    cfg = Config(cache_dir=tmp_path / "cache", raw_dir=tmp_path / "raw")
    provider = Stub(
        Judgment(
            label="entailed", confidence=0.9, evidence_ids=["unknown"], short_rationale="x"
        ).model_dump_json()
    )
    with pytest.raises(ValueError, match="unsupplied"):
        judge(triple(), [evidence()], CallClient(cfg), provider, cfg.judge, 1000)


def test_deduplicate_evidence_and_do_not_cut_negations():
    assert len(prepare_evidence([evidence(), evidence(pid="p2")], 1000)) == 1
    assert prepare_evidence([evidence("not " + ("a" * 500))], 100) == []


def test_conflicting_mock_evidence_is_nei(tmp_path):
    cfg = Config(cache_dir=tmp_path / "cache", raw_dir=tmp_path / "raw")
    first = json.dumps({"subject": "Subject", "predicate": "relation", "object": "Object"})
    second = json.dumps({"subject": "Subject", "predicate": "relation", "object": "incompatible"})
    output, _ = judge(
        triple(),
        [evidence(first), evidence(second, "p2")],
        CallClient(cfg),
        MockProvider(),
        cfg.judge,
        2000,
    )
    assert output.label == "not_enough_information"


def test_human_labels_require_real_review_metadata():
    with pytest.raises(ValidationError, match="annotator"):
        Annotation(
            triple_id="t1",
            human_label="entailed",
            evidence_ids=["p1"],
            evidence_sha256="hash",
            triple_sha256="hash",
        )


def test_paid_calls_fail_closed_before_transport(tmp_path):
    cfg = Config(cache_dir=tmp_path / "cache", raw_dir=tmp_path / "raw", offline=False)
    paid = LLMConfig(
        provider="openai_compatible",
        model="test",
        input_usd_per_million=1,
        output_usd_per_million=1,
    )
    stub = Stub("{}")
    with pytest.raises(ExecutionBlocked, match="approve"):
        CallClient(cfg).call(stub, paid, "generate", "v1", "", {}, Generation)
    assert stub.calls == 0
    cfg.budget_usd = 0.000001
    with pytest.raises(ExecutionBlocked, match="budget"):
        CallClient(cfg, True).call(stub, paid, "generate", "v1", "", {}, Generation)
    assert stub.calls == 0


def test_provider_refusal_and_no_secret_in_error(monkeypatch):
    monkeypatch.setenv("LLMKA_API_KEY", "test-secret-never-log")

    def respond(request):
        assert request.headers["Authorization"] == "Bearer test-secret-never-log"
        return httpx.Response(
            200, json={"choices": [{"message": {"refusal": "cannot"}, "finish_reason": "stop"}]}
        )

    provider = OpenAICompatible(LLMConfig(), Config(), httpx.MockTransport(respond))
    with pytest.raises(ProviderError, match="refused") as error:
        provider.complete("judge", "", {}, Judgment.model_json_schema())
    assert "test-secret" not in str(error.value)


def test_provider_schema_and_usage(monkeypatch):
    monkeypatch.setenv("LLMKA_API_KEY", "fake")

    def respond(request):
        body = json.loads(request.content)
        assert body["response_format"]["json_schema"]["strict"] is True
        assert "seed" not in body
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"triples":[]}'}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 5},
            },
        )

    provider = OpenAICompatible(LLMConfig(), Config(), httpx.MockTransport(respond))
    assert provider.complete("generate", "", {}, Generation.model_json_schema()).input_tokens == 12


def test_public_http_retry_cache_and_offline(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    cfg = Config(
        cache_dir=tmp_path / "cache", raw_dir=tmp_path / "raw", offline=False, request_interval=0
    )
    attempts = []

    def respond(request):
        attempts.append(request)
        return (
            httpx.Response(429, headers={"Retry-After": "1"})
            if len(attempts) == 1
            else httpx.Response(200, json={"search": []})
        )

    client = PublicHTTP(cfg, httpx.MockTransport(respond))
    first = client.get("https://example.org", {"x": 1})
    cfg.offline = True
    assert client.get("https://example.org", {"x": 1}) == first
    assert len(attempts) == 2
    assert client.events[0]["retries"] == 1
    with pytest.raises(RetrievalError, match="cache miss"):
        client.get("https://example.org", {"x": 2})


def test_http_permanent_errors_not_retried(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    cfg = Config(
        cache_dir=tmp_path / "cache", raw_dir=tmp_path / "raw", offline=False, request_interval=0
    )
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(403)

    with pytest.raises(RetrievalError, match="403"):
        PublicHTTP(cfg, httpx.MockTransport(respond)).get("https://example.org", {})
    assert len(calls) == 1


def test_transient_model_retry_accounting(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    cfg = Config(cache_dir=tmp_path / "cache", raw_dir=tmp_path / "raw", offline=False)
    paid = LLMConfig(
        provider="openai_compatible",
        model="test",
        input_usd_per_million=1,
        output_usd_per_million=1,
    )

    class Flaky(Stub):
        def complete(self, *args):
            if self.calls == 0:
                self.calls += 1
                raise TransientProviderError()
            return super().complete(*args)

    client = CallClient(cfg, True)
    client.call(Flaky('{"triples":[]}'), paid, "generate", "v1", "", {}, Generation)
    assert client.events[0]["attempts"] == 2
    assert client.events[0]["retries"] == 1
    assert client.attempts == 2
    assert len(list((tmp_path / "raw/reservations").glob("*.json"))) == 2


def case(cid, qid, kind="homonym"):
    return EntityCase(
        case_id=cid,
        case_type=kind,
        domain="test",
        group_id="g",
        surface_form=cid,
        context="context",
        source_triple=SourceTriple(subject="a", predicate="b", object="c"),
        gold_entity_id=qid,
        gold_label="a",
        gold_description="d",
        source_url="https://example.org",
        verification_status="pending_human_review",
    )


def test_pair_metrics_count_abstention_as_failure():
    cases = [case("a", "Q1"), case("b", "Q2")]
    predictions = {"a": {"selected_entity_id": "Q1"}, "b": {"selected_entity_id": "Q1"}}
    result = entity_metrics(cases, predictions)
    assert result["homonym_conflation_rate"]["value"] == 1
    assert result["homonym_separation_accuracy"]["value"] == 0
    assert result["top1_accuracy"]["value"] == 0.5
    cases = [case("a", "Q1", "synonym"), case("b", "Q1", "synonym")]
    assert entity_metrics(cases, predictions)["synonym_merge_accuracy"]["value"] == 1
    predictions["b"]["selected_entity_id"] = None
    assert entity_metrics(cases, predictions)["synonym_merge_accuracy"]["value"] == 0


def test_retrieval_recall_denominators():
    result = candidate_metrics(
        [case("a", "Q1"), case("b", "Q2")],
        {"a": {"candidates": [{"entity_id": "Q3"}, {"entity_id": "Q1"}]}, "b": {"candidates": []}},
        2,
    )
    assert result["recall_at_k"]["value"] == 0.5
    assert result["mrr"]["value"] == 0.25
