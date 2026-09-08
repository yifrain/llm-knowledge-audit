import unicodedata

from rapidfuzz.fuzz import ratio

from ..models import Resolution, StringCandidate


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    return " ".join("".join(c if c.isalnum() else " " for c in text).split())


class StringBaseline:
    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold

    def resolve(self, surface_form: str, candidates: list[StringCandidate]) -> Resolution:
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
