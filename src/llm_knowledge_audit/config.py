from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, model_validator

from .models import Model


class LLMConfig(Model):
    provider: Literal["mock", "openai_compatible"] = "mock"
    model: str = "deterministic-mock-v1"
    base_url: str = "https://api.openai.com/v1"
    api_key_env: str = "LLMKA_API_KEY"
    temperature: float = Field(default=0, ge=0, le=2)
    send_seed: bool = False
    input_usd_per_million: float = Field(default=0, ge=0)
    output_usd_per_million: float = Field(default=0, ge=0)
    max_output_tokens: int = Field(default=1200, ge=100, le=8000)


class Config(Model):
    mode: Literal["mock", "real"] = "mock"
    dataset: Path = Path("data/benchmark/entity_cases.jsonl")
    mock_candidates: Path = Path("tests/fixtures/candidates.json")
    annotations: Path = Path("data/annotations/human_annotations.jsonl")
    cache_dir: Path = Path("data/cache")
    raw_dir: Path = Path("data/raw")
    results_dir: Path = Path("results")
    offline: bool = True
    require_human_verified: bool = True
    case_limit: int | None = Field(default=None, ge=1)
    candidate_k: int = Field(default=10, ge=1, le=50)
    triples_per_entity: int = Field(default=5, ge=1, le=15)
    seed: int = 42
    min_confidence: float = Field(default=0.6, ge=0, le=1)
    evidence_max_chars: int = Field(default=10000, ge=100, le=24000)
    request_timeout: float = Field(default=30, gt=0, le=120)
    request_interval: float = Field(default=1, ge=0)
    max_attempts: int = Field(default=3, ge=1, le=5)
    max_calls: int = Field(default=50, ge=1)
    budget_usd: float = Field(default=2, gt=0, le=10)
    generator: LLMConfig = Field(default_factory=LLMConfig)
    resolver: LLMConfig = Field(default_factory=LLMConfig)
    judge: LLMConfig = Field(default_factory=LLMConfig)

    @model_validator(mode="after")
    def consistency(self) -> "Config":
        providers = [self.generator, self.resolver, self.judge]
        if self.mode == "mock" and any(x.provider != "mock" for x in providers):
            raise ValueError("Mock mode must use only mock providers")
        if self.mode == "real" and any(x.provider == "mock" for x in providers):
            raise ValueError("Real runs cannot contain mock provider outputs")
        if self.mode == "real" and any(
            x.input_usd_per_million <= 0 or x.output_usd_per_million <= 0 for x in providers
        ):
            raise ValueError("Real providers require explicit positive price estimates")
        return self


def load_config(path: Path) -> Config:
    cfg = Config.model_validate(yaml.safe_load(path.read_text()))
    # Paths are relative to the repository containing configs/, never the caller's cwd.
    root = path.resolve().parent.parent
    for name in (
        "dataset",
        "mock_candidates",
        "annotations",
        "cache_dir",
        "raw_dir",
        "results_dir",
    ):
        value = getattr(cfg, name)
        if not value.is_absolute():
            setattr(cfg, name, root / value)
    return cfg
