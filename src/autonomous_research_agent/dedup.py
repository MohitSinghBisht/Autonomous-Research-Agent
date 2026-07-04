from __future__ import annotations

from difflib import SequenceMatcher

from .models import RawResult


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _is_duplicate(left: RawResult, right: RawResult, threshold: float = 0.9) -> bool:
    if left.url and right.url and left.url == right.url:
        return True

    title_similarity = SequenceMatcher(None, _normalize(left.title), _normalize(right.title)).ratio()
    content_similarity = SequenceMatcher(
        None,
        _normalize(left.content[:300]),
        _normalize(right.content[:300]),
    ).ratio()
    return title_similarity >= threshold or content_similarity >= threshold


def deduplicate_results(results: list[RawResult]) -> list[RawResult]:
    deduped: list[RawResult] = []
    for candidate in results:
        if any(_is_duplicate(candidate, existing) for existing in deduped):
            continue
        deduped.append(candidate)
    return deduped
