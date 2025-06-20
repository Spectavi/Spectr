import logging
import os
import requests
import xml.etree.ElementTree as ET

FMP_API_KEY = os.getenv("FMP_API_KEY")
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
