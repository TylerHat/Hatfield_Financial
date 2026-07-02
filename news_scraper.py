"""
Free, keyless news ingestion for the Ollama reporting POC.

The report generator is NEWS-led, but yfinance's news feed is thin and often
stale. This module pulls headlines from free, publicly published sources and
returns them in the SAME normalized shape data_fetcher.get_news produces, so it
is a drop-in news source for sandbox_ollama.py:

    {'title', 'publisher', 'link', 'publishTime' (ISO str or None), 'summary'}

Sources
-------
- Yahoo Finance RSS  : per-ticker headline feed. Structured, reliable, no key.
- Google News RSS    : search feed (by company name). Broad coverage, gives a
                       publisher + timestamp per item.
- Finviz (HTML)      : the quote-page news table. Richer, but HTML scraping is
                       brittle and ToS-grayer, so it is OPT-IN (off by default).

Why RSS first: the feeds are published expressly for consumption, are stable
XML (parsed here with the stdlib — no feedparser/lxml dependency), and don't
require an API key. Finviz needs BeautifulSoup (already a project dependency).

Politeness / good-citizen notes
-------------------------------
- A descriptive User-Agent is sent on every request.
- Every network call is isolated: one source failing degrades the result, it
  never raises into the caller (mirrors gather_context's best-effort style).
- Requests use normal TLS verification and a short timeout.
- For a full S&P-500 batch, add a shared cache/TTL (as data_fetcher does) and a
  courtesy delay between hosts — see get_free_news's docstring.
"""

import logging
import re
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import requests

log = logging.getLogger("sandbox_ollama.news")

# A real, contactable UA is the polite convention for automated feed reads.
_HEADERS = {
    "User-Agent": (
        "HatfieldInvestmentsBot/0.1 (research; +https://hatfield-financial.com)"
    )
}
_TIMEOUT = 15  # seconds — feeds are small; fail fast rather than stall a batch.

_YAHOO_RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
_GOOGLE_RSS = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
_FINVIZ_URL = "https://finviz.com/quote.ashx?t={ticker}"

_WS_RE = re.compile(r"\s+")
_HTML_TAG_RE = re.compile(r"<[^>]+>")


# ── Shared helpers ────────────────────────────────────────────────────────────
def _clean(text):
    """Collapse whitespace and strip stray HTML tags from feed text."""
    if not text:
        return ""
    text = _HTML_TAG_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def _to_iso(rfc822):
    """RFC-822 feed date ('Wed, 30 Jun 2026 12:00:00 GMT') → ISO-8601 UTC str.

    Returns None on anything unparseable so the caller can sink it to the
    bottom of a newest-first sort, exactly like data_fetcher does.
    """
    if not rfc822:
        return None
    try:
        dt = parsedate_to_datetime(rfc822)
        if dt is None:
            return None
        if dt.tzinfo is None:  # assume UTC when the feed omits an offset
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def _item(title, publisher, link, publish_time, summary):
    """Build the normalized dict, dropping items with no usable title."""
    title = _clean(title)
    if not title:
        return None
    return {
        "title": title,
        "publisher": _clean(publisher) or None,
        "link": (link or "").strip() or None,
        "publishTime": publish_time,
        "summary": _clean(summary),
    }


def _http_get(url):
    """GET with our UA, a timeout, and normal TLS verification.

    Returns the Response, or None on any failure (logged, never raised).
    """
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp
    except requests.RequestException as exc:
        log.warning("news fetch failed: %s (%s)", url, exc)
        return None


# ── RSS sources ───────────────────────────────────────────────────────────────
def _parse_rss(xml_bytes, default_publisher=None):
    """Parse RSS 2.0 <item>s into normalized dicts.

    Handles the two feeds we use: plain items (Yahoo) and items carrying a
    <source> element with the real publisher (Google News, whose <title> is
    'Headline - Publisher').
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        log.warning("RSS parse error: %s", exc)
        return []

    items = []
    for node in root.findall(".//item"):
        title = node.findtext("title") or ""
        link = node.findtext("link")
        summary = node.findtext("description") or ""
        pub = _to_iso(node.findtext("pubDate"))

        # Google News: publisher lives in <source>, and the title ends in
        # ' - Publisher'. Strip that suffix so the headline reads cleanly.
        source_el = node.find("source")
        publisher = default_publisher
        if source_el is not None and (source_el.text or "").strip():
            publisher = source_el.text.strip()
            suffix = f" - {publisher}"
            if title.endswith(suffix):
                title = title[: -len(suffix)]

        built = _item(title, publisher, link, pub, summary)
        if built:
            items.append(built)
    return items


def _yahoo_rss(ticker):
    resp = _http_get(_YAHOO_RSS.format(ticker=quote_plus(ticker)))
    if resp is None:
        return []
    return _parse_rss(resp.content, default_publisher="Yahoo Finance")


def _google_news_rss(ticker, company_name=None):
    # Search the company name when we have it (far less noisy than the bare
    # ticker, which collides with common words); always AND in 'stock'.
    subject = f'"{company_name}"' if company_name else ticker
    query = quote_plus(f"{subject} stock")
    resp = _http_get(_GOOGLE_RSS.format(query=query))
    if resp is None:
        return []
    return _parse_rss(resp.content)


# ── Finviz (optional HTML source) ─────────────────────────────────────────────
def _finviz(ticker):
    """Scrape the Finviz quote-page news table. Opt-in: HTML is brittle.

    Requires BeautifulSoup (already a project dependency). Returns [] rather
    than raising if the page layout shifts or bs4 is unavailable.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        log.warning("Finviz source skipped: beautifulsoup4 not installed")
        return []

    resp = _http_get(_FINVIZ_URL.format(ticker=quote_plus(ticker)))
    if resp is None:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find(id="news-table")
    if table is None:
        log.warning("Finviz layout changed: no #news-table for %s", ticker)
        return []

    items = []
    for row in table.find_all("tr"):
        link_el = row.find("a", class_="tab-link-news") or row.find("a")
        if link_el is None:
            continue
        source_el = row.find("span")
        built = _item(
            link_el.get_text(),
            source_el.get_text() if source_el else "Finviz",
            link_el.get("href"),
            None,  # Finviz times are relative/awkward to normalize — skip.
            "",
        )
        if built:
            items.append(built)
    return items


# ── Orchestration ─────────────────────────────────────────────────────────────
def _dedupe(items):
    """Drop cross-source duplicates, keyed on normalized title then link."""
    seen, out = set(), []
    for it in items:
        key = _WS_RE.sub(" ", it["title"].lower()).strip()
        if key in seen or (it["link"] and it["link"] in seen):
            continue
        seen.add(key)
        if it["link"]:
            seen.add(it["link"])
        out.append(it)
    return out


def get_free_news(ticker, company_name=None, limit=8, include_finviz=False):
    """Aggregate free news for one ticker, newest-first, normalized.

    Parameters
    ----------
    ticker : str
    company_name : str, optional
        Used to make the Google News query specific (e.g. 'Tesla' not 'TSLA').
    limit : int
        Max items returned.
    include_finviz : bool
        Also scrape Finviz's HTML news table (opt-in; brittle).

    Returns
    -------
    list[dict] or None
        The data_fetcher.get_news shape, or None if every source came back
        empty (lets the caller fall back to yfinance).

    Scaling note: for a 500-ticker batch, wrap this in the same cache/TTL
    pattern data_fetcher uses and add a small delay between hosts. Each source
    is already failure-isolated, so a single dead feed won't abort the run.
    """
    ticker = ticker.upper()
    collected = []
    collected.extend(_yahoo_rss(ticker))
    collected.extend(_google_news_rss(ticker, company_name))
    if include_finviz:
        collected.extend(_finviz(ticker))

    items = _dedupe(collected)
    # Newest-first; undated items (e.g. Finviz) sink to the bottom.
    items.sort(key=lambda x: x["publishTime"] or "", reverse=True)
    items = items[:limit]

    if not items:
        log.warning("[%s] no free news from any source", ticker)
        return None
    log.info("[%s] free news: %d items from %d raw", ticker, len(items), len(collected))
    return items


if __name__ == "__main__":  # quick manual check: python news_scraper.py AAPL
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    sym = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    for n in get_free_news(sym, include_finviz="--finviz" in sys.argv) or []:
        print(f"- [{n['publishTime']}] {n['title']}  ({n['publisher']})")
