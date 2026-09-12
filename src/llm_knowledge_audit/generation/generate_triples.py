"""阶段 4：以消歧选中的实体为种子，用 LLM 生成（主语、谓语、宾语）三元组。"""

from ..config import Config, LLMConfig
from ..disambiguation.string_baseline import normalize
from ..models import Candidate, Generation, Triple
from ..providers.base import Provider
from ..providers.client import CallClient
from .prompts import SYSTEM, VERSION


def deduplicate(triples: list[Triple]) -> tuple[list[Triple], int]:
    """按归一化后的（主语、谓语、宾语、宾语类型）去重，保留首次出现的顺序。

    返回（去重后的三元组列表, 被去除的重复条数）——重复条数会进入
    评估的 duplicate_triple_rate 指标。
    """
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
    """为单个实体生成最多 triples_per_entity 条三元组。

    输入：候选实体（含 label、别名、描述）与期望条数；
    输出：（去重后的三元组列表, 重复条数）。

    两道输出防线：
    1. 条数不得超过请求值（防止模型无视数量约束）；
    2. 主语必须是实体的 canonical label——不允许模型改写主语
      （保证生成的三元组仍属于该实体，便于后续证据检索与判定）。
    """
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
