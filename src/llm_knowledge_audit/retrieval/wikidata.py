"""Wikidata 官方 API 客户端：候选实体搜索与实体详情获取。

作为项目的"公开知识来源"之一，为实体消歧阶段提供候选实体。
"""

from __future__ import annotations

from typing import Any

from ..config import Config
from ..models import Candidate
from .http import PublicHTTP, RetrievalError

API = "https://www.wikidata.org/w/api.php"


class Wikidata:
    def __init__(self, cfg: Config):
        # 复用 PublicHTTP：自动获得限速、重试、缓存与审计
        self.http = PublicHTTP(cfg)

    def entities(self, ids: list[str]) -> dict[str, Any]:
        """批量获取实体详情：标签、别名、描述与站点链接（英文为主，含多语言回退）。"""
        return self.http.get(
            API,
            {
                "action": "wbgetentities",
                "ids": "|".join(ids),
                "props": "labels|aliases|descriptions|sitelinks",
                "languages": "en|mul",
                "languagefallback": 1,
                "format": "json",
                "maxlag": 5,
            },
        )

    @staticmethod
    def candidate(qid: str, entity: dict[str, Any], timestamp: str) -> Candidate:
        """把一条实体详情转换为候选实体模型。

        标签优先取英文，其次多语言标签；两者都没有则视为无效候选。
        """
        labels = entity.get("labels", {})
        label = labels.get("en", labels.get("mul", {})).get("value")
        if not label:
            raise RetrievalError(f"No English or multilingual label for {qid}")
        return Candidate.model_validate(
            {
                "entity_id": qid,
                "label": label,
                "aliases": [a["value"] for a in entity.get("aliases", {}).get("en", [])],
                "description": entity.get("descriptions", {}).get("en", {}).get("value", ""),
                "source_url": f"https://www.wikidata.org/wiki/{qid}",
                "retrieved_at": timestamp,
            }
        )

    def search(self, surface_form: str, k: int) -> list[Candidate]:
        """按表面形式搜索实体：先模糊搜索 top-k，再批量取详情。

        保持 API 返回的相关性排序；绝不插入金标准实体、
        绝不使用基准案例上下文来挑选——候选必须来自纯公开搜索。
        """
        search = self.http.get(
            API,
            {
                "action": "wbsearchentities",
                "search": surface_form,
                "language": "en",
                "uselang": "en",
                "type": "item",
                "limit": k,
                "format": "json",
                "maxlag": 5,
            },
        )
        # 去重（dict.fromkeys 保持首次出现顺序），空结果直接返回
        ids = list(dict.fromkeys(c["id"] for c in search["data"].get("search", [])))
        if not ids:
            return []
        record = self.entities(ids)
        # Preserve API rank; never insert the gold entity or select using benchmark context.
        # 保留 API 的排名顺序；已删除（missing）的实体跳过
        return [
            self.candidate(qid, record["data"]["entities"][qid], record["retrieved_at"])
            for qid in ids
            if "missing" not in record["data"]["entities"][qid]
        ]
