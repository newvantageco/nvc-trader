"""
Signal generator — orchestrates all data sources into final BUY/SELL decisions.
This is the pre-Claude layer; Claude calls back into this via tool functions.
"""

from __future__ import annotations
import asyncio
from datetime import datetime, timezone

from loguru import logger

from core.ingestion.news_fetcher import NewsFetcher
from core.ingestion.social_listener import SocialListener
from core.ingestion.economic_calendar import EconomicCalendar
from core.sentiment.finbert_pipeline import SentimentPipeline
from core.sentiment.ner_extractor import NERExtractor
from core.technical.indicator_engine import IndicatorEngine
from core.signals.confluence_engine import ConfluenceEngine, ConfluenceScore
from core.signals.blackout_manager import BlackoutManager
from core.bridge.oanda_client import OandaClient


class SignalGenerator:
    """
    Full signal generation pipeline for a single instrument.
    Returns a ConfluenceScore with all data baked in.
    """

    def __init__(self) -> None:
        self.news     = NewsFetcher()
        self.social   = SocialListener()
        self.calendar = EconomicCalendar()
        self.sentiment= SentimentPipeline()
        self.ner      = NERExtractor()
        self.ta       = IndicatorEngine()
        self.confluence = ConfluenceEngine()
        self.blackout = BlackoutManager()
        self.oanda    = OandaClient()

    async def generate(self, instrument: str) -> dict:
        """
        Full pipeline for one instrument.
        Returns a dict Claude can use for its final decision.
        """
        logger.debug(f"[SIGNAL] Generating signal for {instrument}")

        # Run data fetches in parallel
        ta_task       = self.ta.analyse(instrument)
        news_task     = self.news.fetch_for_instrument(instrument, hours=4)
        social_task   = self.social.fetch_for_instrument(instrument, hours=2)
        price_task    = self.ta.get_price_data(instrument, "H1")
        calendar_task = self.calendar.get_events(hours_ahead=48)

        ta_result, news_articles, social_posts, price_data, cal_events = await asyncio.gather(
            ta_task, news_task, social_task, price_task, calendar_task
        )

        # Combine news + social
        all_articles = news_articles + social_posts

        # Annotate with NER
        annotated = [self.ner.score_article_instruments(a) for a in all_articles]

        # Score sentiment
        scored  = self.sentiment.score_articles(annotated)
        agg     = self.sentiment.aggregate(scored, lookback_hours=4.0)

        # Blackout check
        blackouts = self.calendar.compute_blackouts(cal_events)
        blocked, block_reason = self.blackout.is_blocked(instrument, blackouts)

        # Confluence score
        score_obj = self.confluence.compute(
            instrument     = instrument,
            ta_analysis    = ta_result,
            sentiment_data = agg,
            price_data     = price_data,
        )

        return {
            "instrument":      instrument,
            "score":           score_obj.total_score,
            "direction":       score_obj.direction,
            "tradeable":       score_obj.tradeable and not blocked,
            "blackout":        blocked,
            "blackout_reason": block_reason,
            "entry_price":     score_obj.entry_price,
            "stop_loss":       score_obj.stop_loss,
            "take_profit":     score_obj.take_profit,
            "atr":             score_obj.atr,
            "breakdown": {
                "ta":        score_obj.ta_score,
                "sentiment": score_obj.sentiment_score,
                "momentum":  score_obj.momentum_score,
                "macro":     score_obj.macro_score,
            },
            "sentiment": {
                "score":         agg["score"],
                "bias":          agg["bias"],
                "article_count": agg["article_count"] if "article_count" in agg else len(all_articles),
                "top_events":    agg["top_events"][:3],
            },
            "ta":     ta_result,
            "price":  price_data,
            "reasons": score_obj.reasons,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def scan_watchlist(self, watchlist: list[str]) -> list[dict]:
        """Generate signals for all instruments in the watchlist concurrently."""
        tasks = [self.generate(sym) for sym in watchlist]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        signals = []
        for sym, result in zip(watchlist, results):
            if isinstance(result, Exception):
                logger.warning(f"[SIGNAL] Failed for {sym}: {result}")
            else:
                signals.append(result)
        signals.sort(key=lambda x: x["score"], reverse=True)
        return signals
