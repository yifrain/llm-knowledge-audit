"""运行配置模型与加载入口：所有路径与限额、LLM 参数都在这里定义。"""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, model_validator

from .models import Model


class LLMConfig(Model):
    """单个 LLM 环节（生成/消歧/判定）的调用配置。"""

    provider: Literal["mock", "openai_compatible"] = "mock"
    model: str = "deterministic-mock-v1"
    # base_url / api_key_env：OpenAI 兼容接口地址与 API Key 环境变量名
    base_url: str = "https://api.openai.com/v1"
    api_key_env: str = "LLMKA_API_KEY"
    temperature: float = Field(default=0, ge=0, le=2)
    # send_seed：请求中是否携带随机种子（追求可复现时开启）
    send_seed: bool = False
    # 每百万 token 的输入/输出单价（美元），用于费用预算估算
    input_usd_per_million: float = Field(default=0, ge=0)
    output_usd_per_million: float = Field(default=0, ge=0)
    max_output_tokens: int = Field(default=1200, ge=100, le=8000)


class Config(Model):
    """流水线的全局配置（对应 configs/*.yaml）。"""

    # mode：mock 全程断网用假数据；real 访问公开知识库与付费 LLM API
    mode: Literal["mock", "real"] = "mock"
    # 各数据文件路径（相对路径在 load_config 中会解析为仓库根目录下的绝对路径）
    dataset: Path = Path("data/benchmark/entity_cases.jsonl")
    mock_candidates: Path = Path("tests/fixtures/candidates.json")
    annotations: Path = Path("data/annotations/human_annotations.jsonl")
    cache_dir: Path = Path("data/cache")
    raw_dir: Path = Path("data/raw")
    results_dir: Path = Path("results")
    # offline：real 模式下的额外约束（离线执行公开数据检索）
    offline: bool = True
    # require_human_verified：real 运行要求案例全部通过人工复核
    require_human_verified: bool = True
    # case_limit：最多处理多少个案例（None 表示不限制）
    case_limit: int | None = Field(default=None, ge=1)
    # candidate_k：每个表面形式最多保留多少个候选实体
    candidate_k: int = Field(default=10, ge=1, le=50)
    triples_per_entity: int = Field(default=5, ge=1, le=15)
    seed: int = 42
    # min_confidence：消歧置信度低于该值视为"无法确定"
    min_confidence: float = Field(default=0.6, ge=0, le=1)
    # evidence_max_chars：送入判定环节的单条证据最大字符数
    evidence_max_chars: int = Field(default=10000, ge=100, le=24000)
    request_timeout: float = Field(default=30, gt=0, le=120)
    # request_interval：两次请求的最小间隔（秒），用于限速
    request_interval: float = Field(default=1, ge=0)
    max_attempts: int = Field(default=3, ge=1, le=5)
    # max_calls / budget_usd：单次运行的最大调用次数与预算上限（美元）
    max_calls: int = Field(default=50, ge=1)
    budget_usd: float = Field(default=2, gt=0, le=10)
    # 三个 LLM 环节各自的配置：生成三元组 / 实体消歧 / 事实性判定
    generator: LLMConfig = Field(default_factory=LLMConfig)
    resolver: LLMConfig = Field(default_factory=LLMConfig)
    judge: LLMConfig = Field(default_factory=LLMConfig)

    @model_validator(mode="after")
    def consistency(self) -> "Config":
        """模式与各环节 provider 的一致性校验：

        - mock 模式不允许出现真实 provider；
        - real 模式不允许残留 mock provider（防止混入无意义输出）；
        - real 模式必须显式给出正的价格估算（用于预算管控）。
        """
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
    """从 YAML 加载配置，并把相对路径解析为仓库根目录下的绝对路径。"""
    cfg = Config.model_validate(yaml.safe_load(path.read_text()))
    # Paths are relative to the repository containing configs/, never the caller's cwd.
    # 相对路径以包含 configs/ 的仓库根目录为基准，而不是调用者的当前工作目录。
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
