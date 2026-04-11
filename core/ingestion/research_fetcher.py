"""
Institutional Research & Central Bank Intelligence Fetcher.

Sources (all free / public):
  1. Central bank speech feeds
     - Federal Reserve:  federalreserve.gov/feeds/speeches.xml
     - ECB:              ecb.europa.eu/rss/speeches.rss
     - Bank of England:  bankofengland.co.uk/rss/speeches
     - Bank of Japan:    boj.or.jp RSS
  2. IMF blog / research notes
     - imf.org/en/Publications/rss?language=eng
  3. BIS (Bank for International Settlements) quarterly reviews
     - bis.org/rss/bis_publ.htm
  4. FX Street analyst opinions (public RSS)
  5. Seeking Alpha macro feed (free tier)
  6. ZeroHedge (macro/contrarian) RSS
  7. Brookings Institution economic research

What we extract per item:
  - Title, summary, source, published_at, url
  - NER entities (currencies, countries, instruments affected)
  - Tone: hawkish / dovish / neutral / risk-on / risk-off
  - Impact score (0.0–1.0) based on source authority + topic
"""

from __future__ import annotations

import re
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional
import aiohttp
import xml.etree.ElementTree as ET
from loguru import logger

RESEARCH_FEEDS: list[dict] = [
    {
        "name":     "Federal Reserve Speeches",
        "url":      "https://www.federalreserve.gov/feeds/speeches.xml",
        "currency": ["USD"],
        "authority": 1.0,
    },
    {
        "name":     "ECB Speeches",
        "url":      "https://www.ecb.europa.eu/rss/speeches.rss",
        "currency": ["EUR"],
        "authority": 0.95,
    },
    {
        "name":     "Bank of England Research",
        "url":      "https://www.bankofengland.co.uk/rss/speeches",
        "currency": ["GBP"],
        "authority": 0.95,
    },
    {
        "name":     "IMF Research Notes",
        "url":      "https://www.imf.org/en/Publications/rss?language=eng",
        "currency": ["USD", "EUR", "GBP", "JPY"],
        "authority": 0.90,
    },
    {
        "name":     "BIS Publications",
        "url":      "https://www.bis.org/rss/bis_publ.rss",
        "currency": ["USD", "EUR"],
        "authority": 0.88,
    },
    {
        "name":     "FXStreet Analysis",
        "url":      "https://www.fxstreet.com/rss/news",
        "currency": ["USD", "EUR", "GBP", "JPY", "AUD"],
        "authority": 0.65,
    },
    {
        "name":     "ZeroHedge Macro",
        "url":      "https://feeds.feedburner.com/zerohedge/feed",
        "currency": ["USD", "EUR"],
        "authority": 0.50,
    },
    {
        "name":     "Brookings Economic Studies",
        "url":      "https://www.brookings.edu/topic/economic-studies/feed/",
        "currency": ["USD"],
        "authority": 0.80,
    },
]

# Keywords that indicate hawkish / dovish / risk-on / risk-off tone
HAWKISH_WORDS  = {"hike", "tighten", "restrictive", "inflation", "overheat", "rate rise", "higher rates", "hawkish", "aggressive"}
DOVISH_WORDS   = {"cut", "ease", "accommodative", "stimulus", "recession", "slowdown", "rate cut", "dovish", "pause", "hold"}
RISK_ON_WORDS  = {"growth", "recovery", "expansion", "strong", "robust", "optimistic", "rally", "bullish"}
RISK_OFF_WORDS = {"crisis", "war", "sanctions", "collapse", "default", "contagion", "panic", "fear", "crash", "bear"}

# Cache
_CACHE: dict[str, tuple[datetime, list[dict]]] = {}
_TTL_MINUTES = 30


class ResearchFetcher:
    """Pulls institutional research and central bank intelligence."""

    async def fetch_research(
        self,
        currencies: list[str] | None = None,
        hours: int = 24,
    ) -> list[dict]:
        """
        Returns list of research items, sorted by authority × recency.
        Each item: {title, summary, source, published_at, url,
                    tone, affected_currencies, impact_score, authority}
        """
        feeds = RESEARCH_FEEDS
        if currencies:
            feeds = [f for f in feeds if any(c in f["currency"] for c in currencies)]

        tasks = [self._fetch_feed(feed, hours) for feed in feeds]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        items: list[dict] = []
        for batch in results:
            if isinstance(batch, list):
                items.extend(batch)

        # Sort: most impactful first
        items.sort(key=lambda x: x.get("impact_score", 0), reverse=True)
        return items[:50]   # cap at 50

    async def get_central_bank_stance(self, currency: str) -> dict:
        """
        Returns latest central bank stance for a currency:
        {
          currency, bank_name,
          current_rate, rate_bias (HIKING / CUTTING / HOLDING / UNKNOWN),
          latest_speech_title, latest_speech_date,
          key_phrases, tone_score (-1.0 hawkish → +1.0 dovish)
        }
        """
        cb_map = {
            "USD": ("Federal Reserve Speeches", "Federal Reserve"),
            "EUR": ("ECB Speeches",             "European Central Bank"),
            "GBP": ("Bank of England Research", "Bank of England"),
            "JPY": ("Bank of Japan",            "Bank of Japan"),
        }
        feed_name, bank_name = cb_map.get(currency, (None, "Unknown"))
        if not feed_name:
            return {"currency": currency, "rate_bias": "UNKNOWN", "tone_score": 0}

        feed = next((f for f in RESEARCH_FEEDS if f["name"] == feed_name), None)
        if not feed:
            return {"currency": currency, "rate_bias": "UNKNOWN", "tone_score": 0}

        items = await self._fetch_feed(feed, hours=72)
        if not items:
            return {"currency": currency, "bank_name": bank_name, "rate_bias": "UNKNOWN", "tone_score": 0}

        # Use the most recent item
        latest = items[0]
        tone   = latest.get("tone", "NEUTRAL")

        rate_bias = "HOLDING"
        if tone == "HAWKISH":
            rate_bias = "HIKING"
        elif tone == "DOVISH":
            rate_bias = "CUTTING"

        return {
            "currency":            currency,
            "bank_name":           bank_name,
            "rate_bias":           rate_bias,
            "latest_speech_title": latest.get("title"),
            "latest_speech_date":  latest.get("published_at"),
            "tone":                tone,
            "tone_score":          latest.get("tone_score", 0.0),
            "key_phrases":         latest.get("key_phrases", []),
            "impact_score":        latest.get("impact_score", 0.0),
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _fetch_feed(self, feed: dict, hours: int) -> list[dict]:
        cache_key = f"{feed['name']}:{hours}"
        now = datetime.now(timezone.utc)
        cached = _CACHE.get(cache_key)
        if cached and (now - cached[0]).total_seconds() < _TTL_MINUTES * 60:
            return cached[1]

        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
                headers={"User-Agent": "NVC-Vantage-Research/1.0"}
            ) as session:
                async with session.get(feed["url"]) as resp:
                    if resp.status != 200:
                        return []
                    text = await resp.text()

            items = self._parse_rss(text, feed, hours)
            _CACHE[cache_key] = (now, items)
            return items
        except Exception as e:
            logger.debug(f"[Research] {feed['name']}: {e}")
            return []

    def _parse_rss(self, xml_text: str, feed: dict, hours: int) -> list[dict]:
        items: list[dict] = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return []

        ns = {"atom": "http://www.w3.org/2005/Atom"}

        # Handle both RSS <item> and Atom <entry>
        entries = root.findall(".//item") or root.findall(".//atom:entry", ns)

        for entry in entries:
            def _text(tag: str, default: str = "") -> str:
                el = entry.find(tag) or entry.find(f"atom:{tag}", ns)
                return (el.text or default).strip() if el is not None else default

            title   = _text("title")
            summary = _text("description") or _text("summary") or _text("content")
            url     = _text("link")
            pub_raw = _text("pubDate") or _text("published") or _text("updated")

            # Parse date
            pub_dt = _parse_date(pub_raw)
            if pub_dt and pub_dt < cutoff:
                continue

            text_combined = (title + " " + summary).lower()

            # Tone classification
            h_score = sum(1 for w in HAWKISH_WORDS  if w in text_combined)
            d_score = sum(1 for w in DOVISH_WORDS   if w in text_combined)
            ro_score = sum(1 for w in RISK_ON_WORDS if w in text_combined)
            rf_score = sum(1 for w in RISK_OFF_WORDS if w in text_combined)

            if h_score > d_score and h_score > 0:
                tone = "HAWKISH"
                tone_score = -min(h_score / 5, 1.0)
            elif d_score > h_score and d_score > 0:
                tone = "DOVISH"
                tone_score = min(d_score / 5, 1.0)
            elif rf_score > ro_score and rf_score > 0:
                tone = "RISK_OFF"
                tone_score = 0.0
            elif ro_score > rf_score and ro_score > 0:
                tone = "RISK_ON"
                tone_score = 0.0
            else:
                tone = "NEUTRAL"
                tone_score = 0.0

            # Key phrases extraction (simple)
            key_phrases = [w for w in (HAWKISH_WORDS | DOVISH_WORDS | RISK_OFF_WORDS)
                           if w in text_combined][:5]

            # Impact score: authority × tone intensity × recency bonus
            recency_bonus = 1.0
            if pub_dt:
                age_hours = (datetime.now(timezone.utc) - pub_dt).total_seconds() / 3600
                recency_bonus = max(0.3, 1.0 - age_hours / 72)

            impact = round(feed["authority"] * (0.4 + abs(tone_score) * 0.6) * recency_bonus, 3)

            items.append({
                "title":              title[:200],
                "summary":            summary[:500],
                "source":             feed["name"],
                "authority":          feed["authority"],
                "url":                url,
                "published_at":       pub_dt.isoformat() if pub_dt else pub_raw,
                "tone":               tone,
                "tone_score":         round(tone_score, 2),
                "key_phrases":        key_phrases,
                "affected_currencies": feed["currency"],
                "impact_score":       impact,
            })

        return items


def _parse_date(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    fmts = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d",
    ]
    for fmt in fmts:
        try:
            dt = datetime.strptime(raw.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None
