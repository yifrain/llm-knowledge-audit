"""Resolve Wikipedia via canonical Wikidata sitelinks; retrieve official API extracts.

证据检索的真实实现：通过 Wikidata 站点链接找到英文维基百科条目，
再抓取官方 API 的纯文本摘要，切成证据段落。
"""

import re
from urllib.parse import quote

from ..models import Evidence, Triple
from ..storage import digest
from .wikidata import Wikidata


class WikipediaRetriever:
    def __init__(self, wikidata: Wikidata):
        # 复用同一个 Wikidata 客户端（共享 HTTP 缓存、限速与审计事件）
        self.wikidata = wikidata

    def retrieve(self, entity_id: str, triple: Triple) -> list[Evidence]:
        """为实体 + 三元组检索证据段落。

        流程：Wikidata 查英文站点链接 → 抓取维基百科纯文本摘要
        → 按段落切分（跳过超长段）→ 用关键词重合度排序，取前 8 段。
        """
        # 第一步：实体 → 英文维基百科条目标题（没有条目则无证据）
        record = self.wikidata.entities([entity_id])
        entity = record["data"]["entities"].get(entity_id, {})
        title = entity.get("sitelinks", {}).get("enwiki", {}).get("title")
        if not title:
            return []
        response = self.wikidata.http.get(
            "https://en.wikipedia.org/w/api.php",
            {
                "action": "query",
                # extracts：纯文本摘要；revisions：条目版本号（用于证据追溯）
                "prop": "extracts|revisions",
                "explaintext": 1,
                "exsectionformat": "plain",
                "rvprop": "ids|timestamp",
                "titles": title,
                "redirects": 1,
                "format": "json",
                "formatversion": 2,
                "maxlag": 5,
            },
        )
        result: list[Evidence] = []
        # 三元组谓词与宾语的词集合，用于给段落按相关度打分
        query_words = set(re.findall(r"\w+", (triple.predicate + " " + triple.object).casefold()))
        for page in response["data"].get("query", {}).get("pages", []):
            revision = str(page.get("revisions", [{}])[0].get("revid", "unknown"))
            paragraphs = [s.strip() for s in page.get("extract", "").split("\n") if s.strip()]
            passages = []
            for index, text in enumerate(paragraphs):
                # Keep bounded complete paragraph passages, and provenance to article revision.
                # 只保留完整且长度受限的段落（超长段直接跳过），并记录到条目版本号
                if len(text) > 6000:
                    continue
                passage = Evidence.model_validate(
                    {
                        # passage_id 含版本号与内容哈希：段落内容或版本变化则 ID 变化
                        "passage_id": "wp-" + digest([entity_id, revision, index, text])[:20],
                        "text": text,
                        # oldid 指向具体版本，保证证据可追溯、可复现
                        "source_url": f"https://en.wikipedia.org/w/index.php?title={quote(title)}&oldid={revision}",
                        "retrieved_at": response["retrieved_at"],
                        "revision_id": revision,
                        "license": "CC-BY-SA-4.0; Wikipedia contributors; see source history",
                        "synthetic": False,
                    }
                )
                # 相关度 = 段落与三元组（谓词+宾语）的单词重合数
                score = len(query_words & set(re.findall(r"\w+", text.casefold())))
                passages.append((score, index, passage))
            # 按相关度降序、段落顺序升序排序，最多保留 8 段
            passages.sort(key=lambda item: (-item[0], item[1]))
            result.extend(passage for _, _, passage in passages[:8])
        return result
