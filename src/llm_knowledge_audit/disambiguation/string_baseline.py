"""字符串相似度实体消歧基线：不调用 LLM，作为对照方法。

只使用候选实体的 label 与别名做模糊匹配——刻意不接触描述与上下文，
用于衡量"仅靠表面字符串"能做到什么程度。
"""

import unicodedata

from rapidfuzz.fuzz import ratio

from ..models import Resolution, StringCandidate


def normalize(text: str) -> str:
    """文本归一化：NFKC 标准化 + 小写折叠 + 去标点，只保留字母数字单词序列。

    例如 "Müller-Lüdenscheidt" → "muller ludenscheidt"，
    让比较对大小写、全半角、连字符等差异不敏感。
    """
    text = unicodedata.normalize("NFKC", text).casefold()
    return " ".join("".join(c if c.isalnum() else " " for c in text).split())


class StringBaseline:
    def __init__(self, threshold: float = 0.6):
        # threshold：相似度低于该阈值视为"无法确定"，宁可不选也不乱选
        self.threshold = threshold

    def resolve(self, surface_form: str, candidates: list[StringCandidate]) -> Resolution:
        """从候选中选出与表面形式最相似的实体。

        对每个候选取 label 与全部别名的最高相似度分（rapidfuzz ratio，
        0-1 之间），按分数降序、同分按 QID 字典序排列，取第一名；
        最高分低于阈值时返回"未选中"（selected_entity_id=None）。

        surface_form：待消歧的表面形式
        candidates：候选实体列表，包含 label、别名、QID 等信息
        """
        mention = normalize(surface_form)
        scores = (
            [
                (
                    max(ratio(mention, normalize(label)) / 100 for label in [c.label, *c.aliases]),
                    c.entity_id,
                )
                for c in candidates
            ]
            if mention
            else []
        )
        # Ties use QID lexicographic order, independent of context and gold.
        # 同分按 QID 字典序决胜：与上下文、金标准无关，保证结果确定性。
        scores.sort(key=lambda pair: (-pair[0], pair[1]))
        if not scores or scores[0][0] < self.threshold:
            return Resolution(
                selected_entity_id=None,
                confidence=0,
                short_rationale="No label/alias above string threshold.",
            )
        return Resolution(
            selected_entity_id=scores[0][1],
            confidence=scores[0][0],
            short_rationale="Highest normalized label/alias similarity; QID tie-break.",
        )
