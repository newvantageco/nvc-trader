"""
Social media sentiment listener.
Sources: Twitter/X API v2, Reddit (PRAW), StockTwits REST.
"""

import asyncio
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from loguru import logger

# Symbol → search terms
SYMBOL_SEARCH_TERMS: dict[str, list[str]] = {
    "EURUSD":  ["$EURUSD", "EURUSD", "euro dollar", "EUR/USD"],
    "GBPUSD":  ["$GBPUSD", "GBPUSD", "cable", "pound dollar", "GBP/USD"],
    "USDJPY":  ["$USDJPY", "USDJPY", "dollar yen", "USD/JPY"],
    "AUDUSD":  ["$AUDUSD", "AUDUSD", "aussie dollar", "AUD/USD"],
    "XAUUSD":  ["$XAUUSD", "gold price", "XAUUSD", "#gold", "bullion"],
    "USOIL":   ["crude oil", "WTI oil", "$OIL", "oil price", "OPEC"],
    "UKOIL":   ["brent crude", "brent oil", "north sea oil"],
    "NATGAS":  ["natural gas", "natgas", "$NG", "LNG price"],
    "USDCAD":  ["$USDCAD", "loonie", "CAD dollar"],
    "NZDUSD":  ["$NZDUSD", "kiwi dollar", "NZD"],
}

REDDIT_SUBREDDITS = ["Forex", "investing", "wallstreetbets", "stocks", "Economics", "CryptoCurrency"]
STOCKTWITS_SYMBOLS = ["EURUSD", "GBPUSD", "XAUUSD", "OIL", "USDJPY"]


class SocialListener:
    """
    Aggregates social media sentiment from Twitter/X, Reddit, StockTwits.
    Returns articles in same format as NewsFetcher so SentimentPipeline can score them.
    """

    def __init__(self) -> None:
        self.twitter_token   = os.environ.get("TWITTER_BEARER_TOKEN", "")
        self.reddit_id       = os.environ.get("REDDIT_CLIENT_ID", "")
        self.reddit_secret   = os.environ.get("REDDIT_CLIENT_SECRET", "")
        self.reddit_agent    = os.environ.get("REDDIT_USER_AGENT", "NVCTrader/1.0")

    async def fetch_for_instrument(
        self, instrument: str, hours: float = 2.0
    ) -> list[dict]:
        """Fetch and return social posts relevant to the given instrument."""
        search_terms = SYMBOL_SEARCH_TERMS.get(instrument, [instrument])

        tasks = []
        if self.twitter_token:
            tasks.append(self._fetch_twitter(search_terms, hours))
        tasks.append(self._fetch_reddit(search_terms, instrument, hours))
        tasks.append(self._fetch_stocktwits(instrument))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        posts: list[dict] = []
        for r in results:
            if isinstance(r, list):
                posts.extend(r)

        logger.debug(f"[SOCIAL] {instrument}: {len(posts)} social posts")
        return posts

    # ─── Twitter/X ─────────────────────────────────────────────────────────────

    async def _fetch_twitter(self, terms: list[str], hours: float) -> list[dict]:
        query = " OR ".join(f'"{t}"' for t in terms[:3])
        query += " lang:en -is:retweet"
        start = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")

        params = {
            "query": query,
            "max_results": 100,
            "start_time": start,
            "tweet.fields": "created_at,public_metrics,author_id",
        }
        headers = {"Authorization": f"Bearer {self.twitter_token}"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.twitter.com/2/tweets/search/recent",
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 429:
                        logger.warning("[TWITTER] Rate limited")
                        return []
                    if resp.status != 200:
                        return []
                    data = await resp.json()

            posts = []
            for tweet in data.get("data", []):
                metrics = tweet.get("public_metrics", {})
                # Weight by engagement (retweets + likes signal credibility)
                engagement = metrics.get("retweet_count", 0) + metrics.get("like_count", 0)
                weight = min(0.4 + (engagement / 1000) * 0.2, 0.6)

                try:
                    pub = datetime.strptime(tweet["created_at"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
                except Exception:
                    pub = datetime.now(timezone.utc)

                posts.append({
                    "title": tweet["text"][:280],
                    "description": "",
                    "url": f"https://twitter.com/i/web/status/{tweet['id']}",
                    "source": "twitter",
                    "weight": weight,
                    "published_at": pub,
                    "engagement": engagement,
                })
            return posts
        except Exception as exc:
            logger.warning(f"[TWITTER] Fetch failed: {exc}")
            return []

    # ─── Reddit ─────────────────────────────────────────────────────────────────

    async def _fetch_reddit(
        self, terms: list[str], instrument: str, hours: float
    ) -> list[dict]:
        posts = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        try:
            import praw
            reddit = praw.Reddit(
                client_id=self.reddit_id,
                client_secret=self.reddit_secret,
                user_agent=self.reddit_agent,
            )

            for subreddit_name in REDDIT_SUBREDDITS[:4]:
                subreddit = reddit.subreddit(subreddit_name)
                for submission in subreddit.new(limit=50):
                    pub = datetime.fromtimestamp(submission.created_utc, tz=timezone.utc)
                    if pub < cutoff:
                        continue

                    title_lower = submission.title.lower()
                    body_lower  = (submission.selftext or "").lower()
                    combined    = title_lower + " " + body_lower

                    if not any(t.lower() in combined for t in terms):
                        continue

                    # Upvote ratio as credibility signal
                    upvote_ratio = getattr(submission, "upvote_ratio", 0.5)
                    score = getattr(submission, "score", 0)
                    weight = 0.35 + (min(score, 500) / 500) * 0.15

                    posts.append({
                        "title": submission.title,
                        "description": (submission.selftext or "")[:400],
                        "url": f"https://reddit.com{submission.permalink}",
                        "source": "reddit",
                        "weight": round(weight, 3),
                        "published_at": pub,
                        "upvote_ratio": upvote_ratio,
                        "subreddit": subreddit_name,
                    })

        except ImportError:
            pass
        except Exception as exc:
            logger.warning(f"[REDDIT] Fetch failed: {exc}")

        return posts

    # ─── StockTwits ─────────────────────────────────────────────────────────────

    async def _fetch_stocktwits(self, instrument: str) -> list[dict]:
        """StockTwits has a free REST endpoint for symbol streams."""
        # Map NVC instrument to StockTwits symbol
        symbol_map = {
            "XAUUSD": "GC_F",
            "USOIL":  "CL_F",
            "EURUSD": "EURUSD",
            "GBPUSD": "GBPUSD",
        }
        symbol = symbol_map.get(instrument)
        if not symbol:
            return []

        url = f"https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()

            posts = []
            for msg in data.get("messages", [])[:30]:
                created = msg.get("created_at", "")
                try:
                    pub = datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                except Exception:
                    pub = datetime.now(timezone.utc)

                # StockTwits has a built-in sentiment flag
                entities   = msg.get("entities", {})
                sentiment  = entities.get("sentiment", {})
                st_bias    = sentiment.get("basic") if sentiment else None  # "Bullish" or "Bearish"

                posts.append({
                    "title": msg.get("body", ""),
                    "description": "",
                    "url": f"https://stocktwits.com/message/{msg.get('id')}",
                    "source": "stocktwits",
                    "weight": 0.4,
                    "published_at": pub,
                    "stocktwits_sentiment": st_bias,
                })
            return posts
        except Exception as exc:
            logger.warning(f"[STOCKTWITS] Fetch failed for {instrument}: {exc}")
            return []
