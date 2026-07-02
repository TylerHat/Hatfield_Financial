"""
POC: generate per-stock financial reports with a local Ollama model.

Reports are NEWS-led but grounded in the analytics this site already computes
(buy/momentum signals, Markov regime forecast, fundamentals, analyst view). All
data is gathered here and fed into the prompt — the model fetches nothing itself.

Run from the project root (with the Backend venv active so its deps are importable):

    python sandbox_ollama.py

Output: reports/{TICKER}_{YYYY-MM-DD}.md

Scaling to the full S&P 500
---------------------------
This is a proof-of-concept for the three tickers in TICKERS. To run the whole
index, swap that list for `sp500.get_sp500_tickers()` (importable from Backend).
Note that 500 sequential Ollama generations is a long batch job (roughly
minutes-to-hours depending on the model and GPU) — that productionization, plus
reusing the precomputed `_fetch_all_data()` batch instead of per-ticker fetches,
is the next step beyond this POC, not part of it.
"""

import glob
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta

import requests

# ── Make the Backend analytics importable without running Flask ───────────────
_BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from data_fetcher import (  # noqa: E402
    get_ohlcv,
    get_ticker_info,
    get_analyst_data,
    get_news,
    get_spy_1m_return,
    PRIORITY_HIGH,
)
from routes.recommendations import _build_stock_data  # noqa: E402
from services.markov import analyze_markov  # noqa: E402

from news_scraper import get_free_news  # noqa: E402 — free RSS/HTML news sources

# ── Config ────────────────────────────────────────────────────────────────────
TICKERS = ["MU", "AAPL", "TSLA", "MSFT", "AMZN", "GOOGL", "NVDA", "META", "NFLX", "INTC"]

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
# qwen3:4b fits fully in the RTX 4050's 6 GB VRAM at num_ctx 8192, so it runs on
# the GPU (~5-7x faster than the 8b, which spilled to 100% CPU). Verify placement
# with `ollama ps` — it should read GPU, not CPU.
MODEL = "qwen3:4b"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
LOG_PATH = os.path.join(OUTPUT_DIR, "sandbox_ollama.log")

HISTORY_DAYS = 365    # ~2y of price history for indicators/Markov
NEWS_LIMIT = 8
GEN_TIMEOUT = 600     # seconds — local generation can be slow


# ── Logging ─────────────────────────────────────────────────────────────────--
def _setup_logging():
    """Console (INFO) + file (DEBUG, full tracebacks) so nothing fails quietly.

    The file at reports/sandbox_ollama.log keeps a persistent, timestamped
    record of every run — essential once this scales to a 500-ticker batch.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    logger = logging.getLogger("sandbox_ollama")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()  # idempotent if main() is re-run in the same process

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(levelname)-7s %(message)s"))

    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(message)s")
    )

    logger.addHandler(console)
    logger.addHandler(file_handler)
    return logger


log = _setup_logging()

SYSTEM_INSTRUCTION = (
    "You are a senior equity research analyst writing a concise, investor-facing "
    "research note on ONE stock. Your reader is a retail investor on the Hatfield "
    "Investments platform.\n\n"

    "GROUNDING RULES (non-negotiable):\n"
    "- Use ONLY the data provided in the prompt. Never invent figures, prices, "
    "dates, ratings, or news.\n"
    "- Quote every number exactly as given in the data block. Do NOT rescale, "
    "round differently, or 'correct' a value — the figures are already in their "
    "final display units (percentages are percentages, $ are dollars, P/E is a "
    "multiple). If a number looks surprising, report it as-is; do not silently "
    "adjust it.\n"
    "- If a data point is 'N/A' or missing, say so plainly in one short phrase; "
    "do not speculate to fill the gap.\n"
    "- Some headline news items are about the broader sector or other companies, "
    "not this ticker. Use them only as context and say so explicitly "
    "(e.g. 'sector-wide, not company-specific'). If NO item is specific to this "
    "company, state that directly in one sentence rather than implying coverage.\n\n"

    "STYLE RULES:\n"
    "- Be objective and concise; no hype, no filler, no generic boilerplate like "
    "'investors should monitor developments.'\n"
    "- Translate model internals into plain English. Do NOT print raw engine "
    "artifacts such as the number of observed transitions, raw volatility ratios, "
    "or 'confidence: normal'. Describe volatility and confidence qualitatively "
    "(e.g. 'elevated volatility', 'low-confidence read').\n"
    "- Be internally consistent: a stock cannot be both 'mid-range' and 'near its "
    "high'. Reconcile signals before writing; if they genuinely conflict, name the "
    "conflict in one sentence instead of contradicting yourself.\n"
    "- Map the overall risk score on its 1-10 scale (1 = lowest risk, 10 = "
    "highest); never call a 10 'low risk'.\n"
    "- Do not repeat the same figure in every section. State a number once, then "
    "interpret it.\n\n"

    "REPORT STRUCTURE — Markdown, EXACTLY these sections, in this order:\n"
    "## Summary\n"
    "(2-3 sentences: what the stock is, the single most important takeaway today, "
    "and your directional lean.)\n"
    "## Recent News & Interpretation\n"
    "(Lead here. Summarize the company-specific news and what it means; flag "
    "sector-only items as context.)\n"
    "## Technical & Quant Signals\n"
    "(Bulleted. Price action, RSI, MACD, trend, momentum vs SPY, volatility, "
    "52-week position — each with a one-clause interpretation.)\n"
    "## Fundamentals & Analyst View\n"
    "(Bulleted. Valuation, profitability, growth, leverage, analyst rating and "
    "price-target upside/downside.)\n"
    "## Markov Regime Outlook\n"
    "(Current regime in plain English + what the multi-day forecast implies. No "
    "raw transition counts.)\n"
    "## Bottom Line\n"
    "(A clear, falsifiable thesis: bullish / bearish / neutral and WHY, plus the 1-2 "
    "specific catalysts or levels that would change the view. No hedging cliches.)\n\n"

    "This is data-driven analysis for educational purposes, not investment advice."
)


# ── Formatting helpers (None-safe) ─────────────────────────────────────────────
def _f(val, suffix="", prefix="", decimals=2):
    if val is None:
        return "N/A"
    try:
        return f"{prefix}{float(val):,.{decimals}f}{suffix}"
    except (TypeError, ValueError):
        return f"{prefix}{val}{suffix}"


def _pct(val, decimals=2):
    """Format a value ALREADY in percent units (e.g. 12.5 -> '12.50%').

    Use for backend fields computed as percentages: dayChangePct,
    targetUpsidePct, momentum, fiftyTwoWeekPosition.
    """
    return _f(val, suffix="%", decimals=decimals)


def _pct_frac(val, decimals=1):
    """Format a 0..1 decimal fraction as a percent (e.g. 0.22 -> '22.0%').

    yfinance returns returnOnEquity, earningsGrowth, revenueGrowth,
    grossMargins and the derived fcfYield as fractions, NOT percentages.
    They must be multiplied by 100 before display or the report is off by
    100x (e.g. Apple's ~140% ROE rendered as '1.41%').
    """
    if val is None:
        return "N/A"
    try:
        return f"{float(val) * 100:,.{decimals}f}%"
    except (TypeError, ValueError):
        return "N/A"


def _prob(val):
    """Format a 0..1 probability as a percentage."""
    if val is None:
        return "N/A"
    try:
        return f"{float(val) * 100:.1f}%"
    except (TypeError, ValueError):
        return "N/A"


# ── Context gathering ─────────────────────────────────────────────────────────
def gather_context(ticker):
    """Collect everything the LLM needs for one ticker into a single dict.

    Each sub-fetch is isolated so one failure (e.g. no news) degrades the
    report gracefully instead of aborting it.
    """
    end = datetime.now()
    start = end - timedelta(days=HISTORY_DAYS)

    ctx = {"ticker": ticker, "generated_at": datetime.now()}

    # Price history (also feeds _build_stock_data + Markov)
    try:
        hist = get_ohlcv(ticker, start, end, priority=PRIORITY_HIGH)
    except Exception:  # noqa: BLE001
        log.warning("[%s] get_ohlcv failed", ticker, exc_info=True)
        hist = None
    ctx["hist"] = hist

    # Company info / fundamentals
    try:
        info = get_ticker_info(ticker, priority=PRIORITY_HIGH)
    except Exception:  # noqa: BLE001
        log.warning("[%s] get_ticker_info failed", ticker, exc_info=True)
        info = None
    ctx["info"] = info

    # Full site-computed analytics row (technicals, fundamentals, inline Markov)
    ctx["row"] = None
    if hist is not None:
        try:
            spy_1m = get_spy_1m_return(priority=PRIORITY_HIGH)
            ctx["row"] = _build_stock_data(ticker, info, hist, spy_1m)
        except Exception:  # noqa: BLE001
            log.warning("[%s] _build_stock_data failed", ticker, exc_info=True)
    else:
        log.warning("[%s] no price history — skipping signals", ticker)

    # Detailed Markov regime forecast (full horizon table + recent flips)
    ctx["markov"] = None
    if hist is not None and "Close" in hist:
        try:
            close = hist["Close"].to_numpy(dtype=float)
            dates = [d.strftime("%Y-%m-%d") for d in hist.index]
            ctx["markov"] = analyze_markov(close, dates=dates)
        except Exception:  # noqa: BLE001
            log.warning("[%s] analyze_markov failed", ticker, exc_info=True)
    elif hist is not None:
        log.warning("[%s] price history has no 'Close' column — skipping Markov", ticker)

    # Analyst detail (price targets dict)
    try:
        ctx["analyst"] = get_analyst_data(ticker, priority=PRIORITY_HIGH)
    except Exception:  # noqa: BLE001
        log.warning("[%s] get_analyst_data failed", ticker, exc_info=True)
        ctx["analyst"] = None

    # News (the lead material for the report). Prefer free scraped sources
    # (Yahoo/Google RSS); fall back to yfinance so the report is never newsless.
    ctx["news"] = None
    company_name = (info or {}).get("longName") or (info or {}).get("shortName")
    try:
        ctx["news"] = get_free_news(ticker, company_name=company_name, limit=NEWS_LIMIT)
    except Exception:  # noqa: BLE001
        log.warning("[%s] get_free_news failed", ticker, exc_info=True)
    if not ctx["news"]:
        try:
            log.info("[%s] free news empty — falling back to yfinance", ticker)
            ctx["news"] = get_news(ticker, limit=NEWS_LIMIT, priority=PRIORITY_HIGH)
        except Exception:  # noqa: BLE001
            log.warning("[%s] get_news fallback failed", ticker, exc_info=True)

    # Surface degraded (but non-fatal) context so a thin report isn't a surprise.
    missing = [k for k in ("info", "row", "markov", "analyst", "news") if not ctx.get(k)]
    if missing:
        log.warning("[%s] report will be missing: %s", ticker, ", ".join(missing))

    return ctx


# ── Prompt construction ───────────────────────────────────────────────────────
def _company_block(ctx):
    info = ctx.get("info") or {}
    row = ctx.get("row") or {}
    name = info.get("longName") or info.get("shortName") or row.get("name") or ctx["ticker"]
    lines = [
        f"Company: {name} ({ctx['ticker']})",
        f"Sector: {info.get('sector', 'N/A')}  |  Industry: {info.get('industry', 'N/A')}",
        f"Current price: {_f(row.get('currentPrice') or info.get('currentPrice'), prefix='$')}"
        f"  |  Day change: {_pct(row.get('dayChangePct'))}",
        f"Market cap: {_f(info.get('marketCap'), prefix='$', decimals=0)}",
    ]
    return "\n".join(lines)


def _signals_block(ctx):
    row = ctx.get("row")
    if not row:
        return "Computed signals: unavailable (insufficient price history)."
    lines = [
        f"Price action: {row.get('priceAction', 'N/A')}",
        f"RSI: {_f(row.get('rsiValue'))}  |  MACD: {row.get('macdStatus', 'N/A')}",
        f"Trend alignment: {row.get('trendAlignment', 'N/A')}  |  Momentum vs SPY (1m): {_pct(row.get('momentum'))}",
        # Qualitative status only — the system prompt forbids printing the raw
        # ratio, so don't hand it over for the model to echo.
        f"Volatility: {row.get('volatilityStatus', 'N/A')}",
        f"52-week range: {_f(row.get('fiftyTwoWeekLow'), prefix='$')} - {_f(row.get('fiftyTwoWeekHigh'), prefix='$')}"
        f"  |  Position in range: {_pct(row.get('fiftyTwoWeekPosition'))}",
    ]
    return "\n".join(lines)


def _fundamentals_block(ctx):
    row = ctx.get("row") or {}
    analyst = ctx.get("analyst") or {}
    pt = analyst.get("price_targets") if isinstance(analyst, dict) else None

    de = row.get('debtToEquity')
    de_str = _f(de / 100.0, suffix="x") if isinstance(de, (int, float)) else "N/A"
    lines = [
        f"Forward P/E: {_f(row.get('forwardPE'))}  |  ROE: {_pct_frac(row.get('returnOnEquity'))}",
        f"Debt/Equity: {de_str}  |  Gross margins: {_pct_frac(row.get('grossMargins'))}",
        f"EPS growth: {_pct_frac(row.get('epsGrowth'))}  |  Revenue growth: {_pct_frac(row.get('revenueGrowth'))}"
        f"  |  FCF yield: {_pct_frac(row.get('fcfYield'))}",
        f"Analyst rating: {row.get('analystRecommendation', 'N/A')} ({row.get('recommendationKey', 'n/a')})"
        f"  from {row.get('numberOfAnalysts', 'N/A')} analysts",
        f"Mean target: {_f(row.get('targetMeanPrice'), prefix='$')}"
        f"  |  Implied upside: {_pct(row.get('targetUpsidePct'))}  |  Overall risk: {row.get('overallRisk', 'N/A')}",
    ]
    if isinstance(pt, dict) and pt:
        lines.append(
            "Price-target detail - "
            f"low {_f(pt.get('low'), prefix='$')}, "
            f"mean {_f(pt.get('mean'), prefix='$')}, "
            f"high {_f(pt.get('high'), prefix='$')}, "
            f"current {_f(pt.get('current'), prefix='$')}"
        )
    return "\n".join(lines)


def _markov_block(ctx):
    m = ctx.get("markov")
    if not m:
        return "Markov regime: unavailable."
    lines = [
        f"Current regime: {m.get('current_regime', 'N/A')}"
        f"  (confidence: {'LOW' if m.get('low_confidence') else 'normal'},"
        f" {m.get('transitions_observed', 0)} transitions observed)",
    ]
    fc = m.get("forecast") or {}
    for horizon in ("1d", "3d", "5d", "10d"):
        h = fc.get(horizon)
        if h:
            lines.append(
                f"  {horizon} forecast - Bull {_prob(h.get('bull'))},"
                f" Sideways {_prob(h.get('side'))}, Bear {_prob(h.get('bear'))}"
            )
    transitions = m.get("transitions") or []
    if transitions:
        recent = transitions[-3:]
        flips = "; ".join(f"{t['date']}: {t['from']}->{t['to']}" for t in recent)
        lines.append(f"  Recent regime flips: {flips}")
    return "\n".join(lines)


def _news_block(ctx):
    news = ctx.get("news")
    if not news:
        return "No recent news was available for this ticker."
    items = []
    for i, n in enumerate(news, 1):
        when = (n.get("publishTime") or "")[:10]
        header = f"{i}. {n.get('title')}"
        meta = " - ".join(p for p in (n.get("publisher"), when) if p)
        if meta:
            header += f"  ({meta})"
        summary = n.get("summary")
        if summary:
            summary = summary.strip().replace("\n", " ")
            if len(summary) > 400:
                summary = summary[:400] + "..."
            header += f"\n   {summary}"
        items.append(header)
    return "\n".join(items)


def build_prompt(ctx):
    """Assemble the labeled data block the model writes from."""
    return f"""Write the financial report for {ctx['ticker']} using the data below.

=== COMPANY SNAPSHOT ===
{_company_block(ctx)}

=== RECENT NEWS (most recent first) ===
{_news_block(ctx)}

=== TECHNICAL & QUANT SIGNALS (computed by the platform) ===
{_signals_block(ctx)}

=== FUNDAMENTALS & ANALYST VIEW ===
{_fundamentals_block(ctx)}

=== MARKOV REGIME MODEL ===
{_markov_block(ctx)}

Remember: base the report mainly on the news above, interpret what it means for
the stock, then corroborate with the computed signals. Use only the data given.
"""


# ── Ollama call ───────────────────────────────────────────────────────────────
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_THINK_CLOSE_RE = re.compile(r"</think>", re.IGNORECASE)


def _strip_reasoning(text):
    """Remove qwen3's chain-of-thought from the model output.

    qwen3 emits reasoning either wrapped in <think>...</think> OR — when the
    opening tag is suppressed (our think:False) — as a leading prose block
    terminated by a lone </think> with no opening tag. The original regex only
    matched well-formed pairs, so the tag-less variant leaked the entire
    "Okay, the user wants me to..." monologue into the saved report. Anything up
    to and including the final </think> is reasoning and never belongs in the
    report, so drop it first, then clean up any well-formed pairs that remain.
    """
    matches = list(_THINK_CLOSE_RE.finditer(text))
    if matches:
        text = text[matches[-1].end():]
    return _THINK_RE.sub("", text).strip()


def generate_report(prompt, model=MODEL):
    payload = {
        "model": model,
        "system": SYSTEM_INSTRUCTION,
        "prompt": prompt,
        "stream": False,
        # qwen3 is a reasoning model; the report is grounded in the supplied data
        # block, so the <think> pass adds latency and tokens we strip out anyway.
        "think": False,
        "options": {
            "temperature": 0.3,   # factual, low creativity
            "num_ctx": 8192,      # room for the data block + report
        },
    }
    resp = requests.post(OLLAMA_URL, json=payload, timeout=GEN_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    text = data.get("response", "")
    if not text.strip():
        log.warning("Ollama returned an empty 'response' field")

    # Log throughput (tokens/sec) — the key metric for tuning model/GPU and for
    # estimating a full S&P-500 batch. Ollama reports durations in nanoseconds.
    eval_count = data.get("eval_count") or 0
    eval_ns = data.get("eval_duration") or 0
    if eval_count and eval_ns:
        log.info(
            "generation: %d tokens in %.1fs = %.1f tok/s",
            eval_count, eval_ns / 1e9, eval_count / (eval_ns / 1e9),
        )

    # qwen3 may still emit a chain-of-thought block — strip it from the saved report.
    body = _strip_reasoning(text)
    if not body:
        log.warning("Report body is empty after stripping reasoning block")
    return body


def _delete_old_reports(ticker, keep_path):
    """Remove this ticker's reports from previous runs, keeping only keep_path.

    Without this, every ticker accumulates one file per day forever (and now
    runs every 30 minutes), so reports/ would grow unbounded. Only the latest
    report per ticker is ever needed.
    """
    pattern = os.path.join(OUTPUT_DIR, f"{ticker}_*.md")
    for old_path in glob.glob(pattern):
        if os.path.abspath(old_path) == os.path.abspath(keep_path):
            continue
        try:
            os.remove(old_path)
            log.info("[%s] deleted old report %s", ticker, os.path.basename(old_path))
        except OSError:
            log.warning("[%s] failed to delete old report %s", ticker, old_path, exc_info=True)


def write_report(ctx, body):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    info = ctx.get("info") or {}
    row = ctx.get("row") or {}
    name = info.get("longName") or row.get("name") or ctx["ticker"]
    stamp = ctx["generated_at"]
    filename = f"{ctx['ticker']}_{stamp.strftime('%Y-%m-%d')}.md"
    path = os.path.join(OUTPUT_DIR, filename)
    header = (
        f"# {name} ({ctx['ticker']}) — Financial Report\n\n"
        f"*Generated {stamp.strftime('%Y-%m-%d %H:%M')} by Ollama/{MODEL}. "
        f"Data-grounded; not investment advice.*\n\n---\n\n"
    )
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(header + body + "\n")
    _delete_old_reports(ctx["ticker"], path)
    return path


# ── Orchestration ───────────────────────────────────────────────────────────--
def main():
    log.info("Generating reports with %s for: %s", MODEL, ", ".join(TICKERS))
    log.info("Logging to %s", LOG_PATH)
    wrote, skipped, failed = [], [], []

    for ticker in TICKERS:
        t0 = time.time()
        log.info("[%s] gathering data...", ticker)
        try:
            ctx = gather_context(ticker)
        except Exception:  # noqa: BLE001 — gather is best-effort, never abort the batch
            log.error("[%s] gather_context crashed", ticker, exc_info=True)
            failed.append(ticker)
            continue

        if ctx.get("row") is None and ctx.get("news") is None:
            log.warning("[%s] skipped — no analytics and no news available", ticker)
            skipped.append(ticker)
            continue

        log.info("[%s] generating report...", ticker)
        try:
            body = generate_report(build_prompt(ctx))
        except requests.RequestException:
            log.error("[%s] Ollama request failed", ticker, exc_info=True)
            failed.append(ticker)
            continue
        except Exception:  # noqa: BLE001
            log.error("[%s] report generation crashed", ticker, exc_info=True)
            failed.append(ticker)
            continue

        if not body:
            log.error("[%s] empty report body — not writing a file", ticker)
            failed.append(ticker)
            continue

        path = write_report(ctx, body)
        log.info("[%s] wrote %s  (%.0fs)", ticker, path, time.time() - t0)
        wrote.append(ticker)

    log.info(
        "Done. %d written, %d skipped, %d failed.", len(wrote), len(skipped), len(failed)
    )
    if skipped:
        log.warning("Skipped (no data): %s", ", ".join(skipped))
    if failed:
        log.error("Failed: %s", ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
