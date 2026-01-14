import logging
import os
import json
import html
import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import requests
import xml.etree.ElementTree as ET

# Prefer the generic DATA_API_KEY used by the onboarding dialog, but also accept
# the legacy FMP_API_KEY for existing setups.
FMP_API_KEY = os.getenv("DATA_API_KEY") or os.getenv("FMP_API_KEY")
log = logging.getLogger(__name__)
_TAG_RE = re.compile(r"<[^>]+>")
_MAX_CONTENT_CHARS = int(os.getenv("NEWS_CONTENT_MAX_CHARS") or 0) or None


class _ParagraphParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._capture = 0
        self._skip = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag, attrs) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip += 1
            return
        if tag in {"p"}:
            self._capture += 1

    def handle_endtag(self, tag) -> None:
        if tag in {"script", "style", "noscript"}:
            if self._skip:
                self._skip -= 1
            return
        if tag in {"p"} and self._capture:
            self._capture -= 1

    def handle_data(self, data) -> None:
        if self._skip or not self._capture:
            return
        chunk = data.strip()
        if chunk:
            self._chunks.append(chunk)

    def text(self) -> str:
        return " ".join(self._chunks).strip()


def _strip_html(value: str) -> str:
    if not value:
        return ""
    value = html.unescape(value)
    value = _TAG_RE.sub("", value)
    return " ".join(value.split()).strip()


def _truncate(text: str) -> str:
    if not text or not _MAX_CONTENT_CHARS:
        return text
    if len(text) <= _MAX_CONTENT_CHARS:
        return text
    return text[: _MAX_CONTENT_CHARS].rstrip() + "..."


def _fetch_article_text(url: str) -> str:
    if not url:
        return ""
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        parser = _ParagraphParser()
        parser.feed(resp.text)
        text = parser.text()
        if not text:
            text = _strip_html(resp.text)
        return _truncate(text)
    except Exception as exc:
        log.debug("Article fetch failed for %s: %s", url, exc)
        return ""

def get_latest_news(symbol: str) -> dict:
    """Return the latest news article for *symbol*.

    Returns ``title``, ``date``, ``link``, and ``content`` keys. Content is
    sourced from the data provider when available, otherwise fetched from the
    article URL.
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
                content = article.get("text") or article.get("content") or ""
                if not content and link:
                    content = _fetch_article_text(link)
                return {
                    "title": title,
                    "date": date,
                    "link": link,
                    "content": content,
                }
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
            description = item.findtext("description", default="")
            content = _strip_html(description)
            if not content and link:
                content = _fetch_article_text(link)
            return {
                "title": title,
                "date": date,
                "link": link,
                "content": content,
            }
    except Exception as exc:
        log.error("Web news lookup failed: %s", exc)

    return {"title": "No recent news found.", "date": "", "link": "", "content": ""}


def get_recent_news(symbol: str, days: int = 30) -> list[dict]:
    """Return recent news articles for ``symbol`` from the last ``days`` days.

    Each article dict contains ``title``, ``date``, ``link``, and ``content``
    fields. The function first attempts the Financial Modeling Prep API if
    available and falls back to parsing the Google News RSS feed.
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
                    link = item.get("url", "")
                    content = item.get("text") or item.get("content") or ""
                    if not content and link:
                        content = _fetch_article_text(link)
                    articles.append(
                        {
                            "title": item.get("title", ""),
                            "date": item.get("publishedDate", ""),
                            "link": link,
                            "content": content,
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
            description = item.findtext("description", default="")
            try:
                pub_date = parsedate_to_datetime(pub_text)
            except Exception:
                continue
            if pub_date.replace(tzinfo=None) >= limit_date:
                content = _strip_html(description)
                if not content and link:
                    content = _fetch_article_text(link)
                articles.append(
                    {
                        "title": title,
                        "date": pub_date.isoformat(),
                        "link": link,
                        "content": content,
                    }
                )
        return articles
    except Exception as exc:
        log.error("Web news lookup failed: %s", exc)

    return articles
