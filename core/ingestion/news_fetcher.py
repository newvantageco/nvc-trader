"""
Multi-source news ingestion. Polls RSS feeds, NewsAPI, and GNews.
Maps articles to trading instruments using keyword/entity matching.
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
import feedparser
from loguru import logger
from newsapi import NewsApiClient
from tenacity import retry, stop_after_attempt, wait_exponential

# Country/entity → instrument mapping
INSTRUMENT_KEYWORDS: dict[str, list[str]] = {
    "EURUSD": ["euro", "eurozone", "ecb", "european central bank", "germany", "france", "italy", "eu economy"],
    "GBPUSD": ["pound", "gbp", "bank of england", "boe", "uk economy", "britain", "brexit", "sterling"],
    "USDJPY": ["yen", "boj", "bank of japan", "japan economy", "nikkei", "japanese"],
    "AUDUSD": ["australia", "rba", "reserve bank australia", "aud", "aussie", "iron ore", "china demand"],
    "USDCAD": ["canada", "boc", "bank of canada", "cad", "loonie", "oil sands"],
    "XAUUSD": ["gold", "xauusd", "precious metals", "safe haven", "inflation hedge", "fed rate"],
    "USOIL": ["crude oil", "wti", "opec", "oil supply", "petroleum", "brent", "oil production"],
    "UKOIL": ["brent crude", "north sea", "uk oil", "opec"],
    "NATGAS": ["natural gas", "lng", "gas supply", "gas prices", "energy crisis"],
    "USD":    ["federal reserve", "fed", "fomc", "us economy", "dollar", "cpi", "nfp", "nonfarm", "inflation"],
    "WHEAT":  ["wheat", "grain", "ukraine war", "russia export", "crop yield"],
    "XAGUSD": ["silver", "industrial metals", "solar demand"],
}

RSS_FEEDS = [
    # Tier 1 — high trust
    ("reuters", "https://feeds.reuters.com/reuters/businessNews"),
    ("reuters_fx", "https://feeds.reuters.com/reuters/MostRead"),
    ("ft", "https://www.ft.com/?format=rss"),
    ("cnbc", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("bbc", "http://feeds.bbci.co.uk/news/business/rss.xml"),
    ("ap", "https://feeds.apnews.com/apnews/business"),
    # Tier 2 — medium trust
    ("guardian", "https://www.theguardian.com/business/rss"),
    ("aljazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("seeking_alpha", "https://seekingalpha.com/feed.xml"),
]

SOURCE_WEIGHTS = {
    "reuters": 1.0,
    "ap": 1.0,
    "ft": 0.95,
    "cnbc": 0.85,
    "bbc": 0.80,
    "guardian": 0.75,
    "aljazeera": 0.70,
    "seeking_alpha": 0.65,
    "newsapi": 0.75,
}


class NewsFetcher:
    def __init__(self) -> None:
        api_key = os.environ.get("NEWS_API_KEY")
        self._newsapi = NewsApiClient(api_key=api_key) if api_key else None
        self._cache: dict[str, list[dict]] = {}
        self._last_fetch: dict[str, datetime] = {}

    async def fetch_for_instrument(
        self, instrument: str, hours: float = 4.0
    ) -> list[dict]:
        """
        Fetch and filter news articles relevant to a given instrument.
        Returns a list of article dicts with title, body, source, published_at, weight.
        """
        all_articles = await self._fetch_all(hours=hours)
        keywords = INSTRUMENT_KEYWORDS.get(instrument, [instrument.lower()])

        relevant = []
        for article in all_articles:
            text = f"{article['title']} {article.get('description', '')}".lower()
            if any(kw in text for kw in keywords):
                relevant.append(article)

        logger.debug(f"[NEWS] {instrument}: {len(relevant)} relevant articles (from {len(all_articles)} total)")
        return relevant

    async def fetch_breaking_news(self, minutes: int = 30) -> list[dict]:
        """Fetch only very recent news (past N minutes) for event detection."""
        all_articles = await self._fetch_all(hours=minutes / 60)
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        return [a for a in all_articles if a["published_at"] > cutoff]

    async def _fetch_all(self, hours: float = 4.0) -> list[dict]:
        """Aggregate from all sources with caching."""
        cache_key = f"{hours:.1f}"
        last = self._last_fetch.get(cache_key)
        if last and (datetime.now(timezone.utc) - last).seconds < 60:
            return self._cache.get(cache_key, [])

        tasks = [self._fetch_rss(name, url) for name, url in RSS_FEEDS]
        if self._newsapi:
            tasks.append(self._fetch_newsapi(hours))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        articles: list[dict] = []
        for result in results:
            if isinstance(result, list):
                articles.extend(result)

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        articles = [a for a in articles if a["published_at"] > cutoff]

        # Deduplicate by URL — same story syndicated from multiple feeds counts once.
        # If URL is missing, fall back to normalised title (lowercase, stripped).
        seen: set[str] = set()
        deduped: list[dict] = []
        for article in articles:
            key = article.get("url") or article.get("title", "").lower().strip()
            if key and key not in seen:
                seen.add(key)
                deduped.append(article)

        deduped.sort(key=lambda x: x["published_at"], reverse=True)

        self._cache[cache_key] = deduped
        self._last_fetch[cache_key] = datetime.now(timezone.utc)
        logger.debug(f"[NEWS] Fetched {len(articles)} articles, {len(deduped)} after dedup (from {hours:.1f}h window)")
        return deduped

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _fetch_rss(self, source_name: str, url: str) -> list[dict]:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(url) as resp:
                    text = await resp.text()

            feed = feedparser.parse(text)
            articles = []
            weight = SOURCE_WEIGHTS.get(source_name, 0.7)

            for entry in feed.entries[:30]:
                pub = entry.get("published_parsed")
                if pub:
                    published_at = datetime(*pub[:6], tzinfo=timezone.utc)
                else:
                    published_at = datetime.now(timezone.utc)

                articles.append({
                    "title": entry.get("title", ""),
                    "description": entry.get("summary", "")[:500],
                    "url": entry.get("link", ""),
                    "source": source_name,
                    "weight": weight,
                    "published_at": published_at,
                })
            return articles

        except Exception as exc:
            logger.warning(f"[RSS] Failed to fetch {source_name}: {exc}")
            return []

    async def _fetch_newsapi(self, hours: float) -> list[dict]:
        if not self._newsapi:
            return []
        try:
            from_date = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S")
            response = self._newsapi.get_everything(
                q="forex OR currency OR commodity OR oil OR gold OR federal reserve OR ECB",
                language="en",
                sort_by="publishedAt",
                from_param=from_date,
                page_size=50,
            )
            articles = []
            for a in response.get("articles", []):
                pub_str = a.get("publishedAt", "")
                try:
                    published_at = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                except Exception:
                    published_at = datetime.now(timezone.utc)

                articles.append({
                    "title": a.get("title", ""),
                    "description": a.get("description", "")[:500],
                    "url": a.get("url", ""),
                    "source": "newsapi",
                    "weight": SOURCE_WEIGHTS["newsapi"],
                    "published_at": published_at,
                })
            return articles
        except Exception as exc:
            logger.warning(f"[NewsAPI] Fetch failed: {exc}")
            return []
