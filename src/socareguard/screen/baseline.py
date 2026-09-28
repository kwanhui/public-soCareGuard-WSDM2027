"""Generic harm classifier, kept as the contrast baseline (what a safety filter would say)."""

from __future__ import annotations

import os
from functools import lru_cache


def moderation_flags(text: str, threshold: float = 0.5) -> list[str]:
    """OpenAI omni-moderation categories above threshold. Empty list when no key is configured."""
    if not os.environ.get("OPENAI_API_KEY"):
        return []

    r = _client().moderations.create(model="omni-moderation-latest", input=text[:10000])
    scores = r.results[0].category_scores.model_dump()
    return sorted(k for k, v in scores.items() if v is not None and v >= threshold)


@lru_cache(maxsize=1)
def _client():
    from openai import OpenAI

    return OpenAI()
