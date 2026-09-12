"""检索模块的公共接口定义。"""

from typing import Protocol

from ..models import Evidence, Triple


class EvidenceRetriever(Protocol):
    """证据检索器的协议接口：给定实体与三元组，返回证据段落列表。

    Pipeline 里用 MockEvidenceRetriever 作默认实现，real 模式换为
    WikipediaRetriever——两者只要满足这个协议即可互换。
    """

    def retrieve(self, entity_id: str, triple: Triple) -> list[Evidence]: ...
