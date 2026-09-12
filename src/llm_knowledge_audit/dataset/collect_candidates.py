"""Public candidate snapshot writer; deliberately has no gold-enrichment behavior.

公开候选实体快照生成器：只如实记录公开知识库的搜索结果，
刻意不做任何"金标准增强"（绝不把正确答案混进候选，防止泄漏）。
"""

from pathlib import Path

from ..config import Config
from ..retrieval.wikidata import Wikidata
from ..storage import write_new
from .validate_cases import load_cases


def collect(cfg: Config, output: Path) -> None:
    """为数据集中的每个表面形式（surface_form）生成候选实体快照。

    用途：mock 模式下 pipeline 的 collect-candidates 阶段读取这个快照文件
    （tests/fixtures/candidates.json），从而全程断网、结果可复现。

    流程：
    1. 加载数据集案例，按表面形式去重排序——同一表面形式只搜索一次；
    2. 对每个表面形式调用 Wikidata 搜索，取前 candidate_k 个候选实体；
    3. 用 write_new 原子写入快照文件（已存在则报错，不覆盖）。
    """
    source = Wikidata(cfg)
    cases = load_cases(cfg.dataset)
    snapshots = {}
    # 表面形式去重 + 排序：保证快照内容稳定、可复现
    for surface in sorted({c.surface_form for c in cases}):
        snapshots[surface] = [
            c.model_dump(mode="json") for c in source.search(surface, cfg.candidate_k)
        ]
    write_new(output, snapshots)
