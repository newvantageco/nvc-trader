"""
FinBERT-based sentiment analysis pipeline.
Uses ProsusAI/finbert — a BERT model fine-tuned on financial text.
Scores are aggregated with time-decay and source weighting.
"""

import math
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from loguru import logger


@lru_cache(maxsize=1)
def _load_finbert():
    """Lazy-load FinBERT model (only once, cached)."""
    from transformers import pipeline as hf_pipeline
    logger.info("[FinBERT] Loading ProsusAI/finbert...")
    pipe = hf_pipeline(
        "text-classification",
        model="ProsusAI/finbert",
        top_k=None,
        truncation=True,
        max_length=512,
    )
    logger.info("[FinBERT] Model loaded.")
    return pipe


LABEL_TO_SCORE = {
    "positive": 1.0,
    "neutral": 0.0,
    "negative": -1.0,
}

# Exponential decay constant (λ) — per hour
DECAY_BREAKING = 0.30   # breaking news fades fast
DECAY_ECONOMIC = 0.10   # economic data stays relevant longer
DECAY_GENERAL = 0.20    # general news


class SentimentPipeline:
    def __init__(self) -> None:
        self._pipe = None  # lazy load

    def _ensure_loaded(self):
        if self._pipe is None:
            self._pipe = _load_finbert()

    def score_articles(self, articles: list[dict]) -> list[dict]:
        """
        Score a list of articles with FinBERT sentiment.
        Appends sentiment_score (-1 to +1), sentiment_label, and confidence.
        """
        if not articles:
            return []

        self._ensure_loaded()

        texts = [
            f"{a['title']}. {a.get('description', '')}"[:512]
            for a in articles
        ]

        try:
            results = self._pipe(texts)
        except Exception as exc:
            logger.warning(f"[FinBERT] Inference failed: {exc}")
            return articles

        scored = []
        for article, preds in zip(articles, results):
            best = max(preds, key=lambda x: x["score"])
            raw_score = LABEL_TO_SCORE.get(best["label"].lower(), 0.0)

            # Scale by confidence
            score = raw_score * best["score"]

            scored.append({
                **article,
                "sentiment_score": score,
                "sentiment_label": best["label"].lower(),
                "sentiment_confidence": best["score"],
            })

        return scored

    def aggregate(
        self, scored_articles: list[dict], lookback_hours: float = 4.0
    ) -> dict:
        """
        Aggregate scored articles into a single instrument sentiment signal.
        Applies time-decay and source weighting.
        """
        if not scored_articles:
            return {
                "score": 0.0,
                "normalised": 0.5,
                "bias": "neutral",
                "top_events": [],
                "sources": {},
            }

        now = datetime.now(timezone.utc)
        weighted_sum = 0.0
        weight_total = 0.0
        sources: dict[str, int] = {}
        events = []

        for a in scored_articles:
            # Time decay
            age_hours = (now - a["published_at"]).total_seconds() / 3600
            decay = _decay_lambda(a["source"])
            time_weight = math.exp(-decay * age_hours)

            # Source credibility weight
            source_weight = a.get("weight", 0.7)

            # Combined weight
            w = time_weight * source_weight * a.get("sentiment_confidence", 1.0)

            weighted_sum += a["sentiment_score"] * w
            weight_total += w

            sources[a["source"]] = sources.get(a["source"], 0) + 1

            if abs(a["sentiment_score"]) > 0.3:
                events.append({
                    "title": a["title"],
                    "source": a["source"],
                    "score": a["sentiment_score"],
                    "published_at": a["published_at"].isoformat(),
                })

        final_score = weighted_sum / weight_total if weight_total > 0 else 0.0
        final_score = max(-1.0, min(1.0, final_score))
        normalised = (final_score + 1.0) / 2.0  # 0.0–1.0

        if final_score > 0.15:
            bias = "bullish"
        elif final_score < -0.15:
            bias = "bearish"
        else:
            bias = "neutral"

        events.sort(key=lambda x: abs(x["score"]), reverse=True)

        return {
            "score": round(final_score, 4),
            "normalised": round(normalised, 4),
            "bias": bias,
            "top_events": events[:10],
            "sources": sources,
        }


def _decay_lambda(source: str) -> float:
    """Return appropriate decay constant based on source type."""
    social_sources = {"twitter", "reddit", "stocktwits"}
    economic_sources = {"reuters", "ap", "ft", "bloomberg"}
    if source in social_sources:
        return DECAY_BREAKING
    if source in economic_sources:
        return DECAY_ECONOMIC
    return DECAY_GENERAL
