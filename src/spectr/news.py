import logging
import os
import json
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
import requests
import xml.etree.ElementTree as ET

# Prefer the generic DATA_API_KEY used by the onboarding dialog, but also accept
# the legacy FMP_API_KEY for existing setups.
FMP_API_KEY = os.getenv("DATA_API_KEY") or os.getenv("FMP_API_KEY")
log = logging.getLogger(__name__)

def get_latest_news(symbol: str) -> str:
    """Return a short string describing the latest news article for *symbol*.

    Tries the Financial Modeling Prep (FMP) API first if ``FMP_API_KEY`` is set.
    Falls back to parsing the Google News RSS feed if the API lookup fails.
    """
    # First try the FMP stock_news endpoint
    if FMP_API_KEY:
        url = (
            f"https://financialmodelingprep.com/api/v3/stock_news?"
            f"tickers={symbol.upper()}&limit=1&apikey={FMP_API_KEY}"
        )
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and data:
                article = data[0]
                title = article.get("title", "")
                date = article.get("publishedDate", "")
                link = article.get("url", "")
                return f"{title} ({date}) {link}"
        except Exception as exc:
            log.error("FMP news lookup failed: %s", exc)

    # Fall back to Google News RSS feed
    feed_url = (
        "https://news.google.com/rss/search?"
        f"q={symbol}%20stock&hl=en-US&gl=US&ceid=US:en"
    )
    try:
        resp = requests.get(feed_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        item = root.find("channel/item")
        if item is not None:
            title = item.findtext("title", default="")
            date = item.findtext("pubDate", default="")
            link = item.findtext("link", default="")
            return f"{title} ({date}) {link}"
    except Exception as exc:
        log.error("Web news lookup failed: %s", exc)

    return "No recent news found."


def get_recent_news(symbol: str, days: int = 30) -> list[dict]:
    """Return recent news articles for ``symbol`` from the last ``days`` days.

    Each article dict contains ``title``, ``date``, and ``link`` fields.  The
    function first attempts the Financial Modeling Prep API if available and
    falls back to parsing the Google News RSS feed.
    """

    articles: list[dict] = []

    if FMP_API_KEY:
        since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        url = (
            "https://financialmodelingprep.com/api/v3/stock_news?"
            f"tickers={symbol.upper()}&from={since}&apikey={FMP_API_KEY}"
        )
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                for item in data:
                    articles.append(
                        {
                            "title": item.get("title", ""),
                            "date": item.get("publishedDate", ""),
                            "link": item.get("url", ""),
                        }
                    )
                return articles
        except Exception as exc:
            log.error("FMP news lookup failed: %s", exc)

    feed_url = (
        "https://news.google.com/rss/search?"
        f"q={symbol}%20stock&hl=en-US&gl=US&ceid=US:en"
    )
    try:
        resp = requests.get(feed_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        limit_date = datetime.utcnow() - timedelta(days=days)
        for item in root.findall("channel/item"):
            title = item.findtext("title", default="")
            pub_text = item.findtext("pubDate", default="")
            link = item.findtext("link", default="")
            try:
                pub_date = parsedate_to_datetime(pub_text)
            except Exception:
                continue
            if pub_date.replace(tzinfo=None) >= limit_date:
                articles.append(
                    {"title": title, "date": pub_date.isoformat(), "link": link}
                )
        return articles
    except Exception as exc:
        log.error("Web news lookup failed: %s", exc)

    return articles
