"""
Named Entity Recognition — extracts geopolitical entities from news text
and maps them to affected trading instruments.
"""

from __future__ import annotations
from functools import lru_cache
from typing import Any

from loguru import logger

# ─── Country / Entity → Instruments mapping ───────────────────────────────────
ENTITY_INSTRUMENT_MAP: dict[str, dict] = {
    # Major economies → currencies
    "united states": {"instruments": ["EURUSD", "USDJPY", "USDCAD", "USDCHF", "XAUUSD"], "currency": "USD"},
    "us ":           {"instruments": ["EURUSD", "USDJPY", "USDCAD", "XAUUSD"], "currency": "USD"},
    "america":       {"instruments": ["EURUSD", "USDJPY", "USDCAD"], "currency": "USD"},
    "federal reserve": {"instruments": ["EURUSD", "USDJPY", "XAUUSD", "USDCAD"], "currency": "USD"},
    "fed ":          {"instruments": ["EURUSD", "USDJPY", "XAUUSD"], "currency": "USD"},
    "fomc":          {"instruments": ["EURUSD", "USDJPY", "XAUUSD"], "currency": "USD"},
    "eurozone":      {"instruments": ["EURUSD", "EURJPY"], "currency": "EUR"},
    "european":      {"instruments": ["EURUSD", "EURJPY"], "currency": "EUR"},
    "ecb":           {"instruments": ["EURUSD", "EURJPY"], "currency": "EUR"},
    "germany":       {"instruments": ["EURUSD", "EURJPY"], "currency": "EUR"},
    "france":        {"instruments": ["EURUSD"], "currency": "EUR"},
    "united kingdom":{"instruments": ["GBPUSD", "GBPJPY"], "currency": "GBP"},
    "britain":       {"instruments": ["GBPUSD", "GBPJPY"], "currency": "GBP"},
    "bank of england":{"instruments": ["GBPUSD", "GBPJPY"], "currency": "GBP"},
    "boe":           {"instruments": ["GBPUSD", "GBPJPY"], "currency": "GBP"},
    "japan":         {"instruments": ["USDJPY", "EURJPY", "GBPJPY"], "currency": "JPY"},
    "bank of japan": {"instruments": ["USDJPY", "EURJPY", "GBPJPY"], "currency": "JPY"},
    "boj":           {"instruments": ["USDJPY", "EURJPY", "GBPJPY"], "currency": "JPY"},
    "australia":     {"instruments": ["AUDUSD"], "currency": "AUD"},
    "rba":           {"instruments": ["AUDUSD"], "currency": "AUD"},
    "canada":        {"instruments": ["USDCAD"], "currency": "CAD"},
    "bank of canada":{"instruments": ["USDCAD"], "currency": "CAD"},
    "new zealand":   {"instruments": ["NZDUSD"], "currency": "NZD"},
    "switzerland":   {"instruments": ["USDCHF"], "currency": "CHF"},
    # Commodity drivers
    "opec":          {"instruments": ["USOIL", "UKOIL"], "currency": None},
    "saudi arabia":  {"instruments": ["USOIL", "UKOIL"], "currency": None},
    "russia":        {"instruments": ["USOIL", "UKOIL", "NATGAS"], "currency": None},
    "crude oil":     {"instruments": ["USOIL", "UKOIL"], "currency": None},
    "brent":         {"instruments": ["UKOIL"], "currency": None},
    "wti":           {"instruments": ["USOIL"], "currency": None},
    "natural gas":   {"instruments": ["NATGAS"], "currency": None},
    "ukraine":       {"instruments": ["WHEAT", "NATGAS", "USOIL"], "currency": None},
    "gold":          {"instruments": ["XAUUSD"], "currency": None},
    "silver":        {"instruments": ["XAGUSD"], "currency": None},
    "inflation":     {"instruments": ["XAUUSD", "EURUSD", "GBPUSD"], "currency": None},
    "interest rate": {"instruments": ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"], "currency": None},
    "cpi":           {"instruments": ["EURUSD", "GBPUSD", "XAUUSD"], "currency": None},
    "gdp":           {"instruments": ["EURUSD", "GBPUSD", "AUDUSD"], "currency": None},
    "nonfarm":       {"instruments": ["EURUSD", "USDJPY", "XAUUSD"], "currency": None},
    "payroll":       {"instruments": ["EURUSD", "USDJPY", "XAUUSD"], "currency": None},
    "recession":     {"instruments": ["XAUUSD", "USDJPY", "USDCHF"], "currency": None},
    "war":           {"instruments": ["XAUUSD", "USOIL", "NATGAS"], "currency": None},
    "sanctions":     {"instruments": ["USOIL", "NATGAS", "XAUUSD"], "currency": None},
    "china":         {"instruments": ["AUDUSD", "USOIL", "XAUUSD"], "currency": None},
}

EVENT_IMPACT_WEIGHTS: dict[str, float] = {
    "interest rate decision": 1.0,
    "rate hike":              0.95,
    "rate cut":               0.95,
    "quantitative easing":    0.90,
    "qe":                     0.90,
    "non-farm payroll":        0.90,
    "nfp":                    0.90,
    "cpi":                    0.85,
    "inflation":               0.80,
    "gdp":                    0.80,
    "trade war":              0.75,
    "tariff":                 0.70,
    "sanctions":              0.70,
    "war":                    0.65,
    "election":               0.60,
    "referendum":             0.55,
    "strike":                 0.45,
    "natural disaster":       0.40,
}


@lru_cache(maxsize=1)
def _load_spacy():
    """Load spaCy model once and cache it."""
    try:
        import spacy
        nlp = spacy.load("en_core_web_lg")
        logger.info("[NER] spaCy en_core_web_lg loaded")
        return nlp
    except Exception as exc:
        logger.warning(f"[NER] spaCy load failed: {exc} — falling back to keyword matching")
        return None


class NERExtractor:
    """
    Extracts entities from news text and maps them to instruments.
    Uses spaCy for proper NER, falls back to keyword matching.
    """

    def __init__(self) -> None:
        self._nlp = None  # lazy load

    def extract(self, text: str) -> dict:
        """
        Extract entities and return a dict of affected instruments with impact scores.

        Returns:
            {
              "instruments": {"EURUSD": 0.85, "XAUUSD": 0.70},
              "entities": ["Federal Reserve", "United States"],
              "event_type": "interest rate decision",
              "event_weight": 1.0,
            }
        """
        text_lower = text.lower()
        instruments: dict[str, float] = {}
        entities_found: list[str] = []

        # ── spaCy NER ──────────────────────────────────────────────────────────
        if self._nlp is None:
            self._nlp = _load_spacy()

        if self._nlp:
            doc = self._nlp(text[:1000])
            for ent in doc.ents:
                if ent.label_ in ("GPE", "ORG", "NORP"):
                    key = ent.text.lower()
                    entities_found.append(ent.text)
                    match = self._lookup(key)
                    for instr, score in match.items():
                        instruments[instr] = max(instruments.get(instr, 0), score)

        # ── Keyword fallback (always runs — catches things spaCy may miss) ──────
        for keyword, data in ENTITY_INSTRUMENT_MAP.items():
            if keyword in text_lower:
                if keyword.strip() not in [e.lower() for e in entities_found]:
                    entities_found.append(keyword.strip())
                for instr in data["instruments"]:
                    instruments[instr] = max(instruments.get(instr, 0), 0.7)

        # ── Detect event type ──────────────────────────────────────────────────
        event_type   = "general"
        event_weight = 0.5
        for event, weight in EVENT_IMPACT_WEIGHTS.items():
            if event in text_lower and weight > event_weight:
                event_type   = event
                event_weight = weight

        return {
            "instruments": instruments,
            "entities": list(set(entities_found))[:10],
            "event_type": event_type,
            "event_weight": event_weight,
        }

    def _lookup(self, key: str) -> dict[str, float]:
        """Direct entity → instrument lookup."""
        # Try exact match
        if key in ENTITY_INSTRUMENT_MAP:
            return {i: 0.85 for i in ENTITY_INSTRUMENT_MAP[key]["instruments"]}
        # Partial match
        for entity_key, data in ENTITY_INSTRUMENT_MAP.items():
            if entity_key.strip() in key or key in entity_key:
                return {i: 0.75 for i in data["instruments"]}
        return {}

    def score_article_instruments(self, article: dict) -> dict:
        """Annotate an article with its affected instruments."""
        text = f"{article.get('title', '')} {article.get('description', '')}"
        extraction = self.extract(text)
        return {**article, "ner": extraction}
