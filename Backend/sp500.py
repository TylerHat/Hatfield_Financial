"""
S&P 500 constituent tickers — fetched dynamically from Wikipedia with
an in-memory 24-hour cache and a static fallback list.
"""

import logging
import threading
import time

import pandas as pd

logger = logging.getLogger(__name__)

# ── In-memory cache ────────────────────────────────────────────────────────────
_cached_tickers = None
_cache_timestamp = 0.0
_cache_lock = threading.Lock()
_CACHE_TTL = 86400  # 24 hours

# ── Static fallback (current as of early 2025, delisted tickers removed) ──────
_FALLBACK_TICKERS = [
    "AAPL", "ABBV", "ABT", "ACN", "ADBE", "ADI", "ADM", "ADP", "ADSK", "AEE",
    "AEP", "AES", "AFL", "AIG", "AIZ", "AJG", "AKAM", "ALB", "ALGN", "ALK",
    "ALL", "ALLE", "AMAT", "AMCR", "AMD", "AME", "AMGN", "AMP", "AMT", "AMZN",
    "ANET", "ANSS", "AON", "AOS", "APA", "APD", "APH", "APTV", "ARE", "ATO",
    "AVB", "AVGO", "AVY", "AWK", "AXP", "AZO", "BA", "BAC", "BAX",
    "BBY", "BDX", "BEN", "BF.B", "BG", "BIIB", "BIO", "BK", "BKNG",
    "BKR", "BLK", "BMY", "BR", "BRK.B", "BRO", "BSX", "BWA", "BXP", "C",
    "CAG", "CAH", "CARR", "CAT", "CB", "CBOE", "CBRE", "CCI", "CCL",
    "CDNS", "CDW", "CE", "CEG", "CF", "CFG", "CHD", "CHRW", "CHTR", "CI",
    "CINF", "CL", "CLX", "CMA", "CMCSA", "CME", "CMG", "CMI", "CMS", "CNC",
    "CNP", "COF", "COO", "COP", "COST", "CPB", "CPRT", "CPT", "CRL", "CRM",
    "CRWD", "CSCO", "CSGP", "CSX", "CTAS", "CTRA", "CTSH", "CTVA", "CVS",
    "CVX", "CZR", "D", "DAL", "DD", "DE", "DECK", "DFS", "DG", "DGX",
    "DHI", "DHR", "DIS", "DLR", "DLTR", "DOV", "DOW", "DPZ", "DRI",
    "DTE", "DUK", "DVA", "DVN", "DXCM", "EA", "EBAY", "ECL", "ED",
    "EFX", "EIX", "EL", "EMN", "EMR", "ENPH", "EOG", "EPAM", "EQIX", "EQR",
    "EQT", "ES", "ESS", "ETN", "ETR", "ETSY", "EVRG", "EW", "EXC", "EXPD",
    "EXPE", "EXR", "F", "FANG", "FAST", "FBHS", "FCX", "FDS", "FDX", "FE",
    "FFIV", "FIS", "FISV", "FITB", "FLT", "FMC", "FOX", "FOXA", "FRT",
    "FTNT", "FTV", "GD", "GE", "GEHC", "GEN", "GILD", "GIS", "GL", "GLW",
    "GM", "GNRC", "GOOG", "GOOGL", "GPC", "GPN", "GRMN", "GS", "GWW", "HAL",
    "HAS", "HBAN", "HCA", "HD", "HOLX", "HON", "HPE", "HPQ", "HRL", "HSIC",
    "HST", "HSY", "HUBB", "HUM", "HWM", "IBM", "ICE", "IDXX", "IEX", "IFF",
    "ILMN", "INCY", "INTC", "INTU", "INVH", "IP", "IPG", "IQV", "IR", "IRM",
    "ISRG", "IT", "ITW", "IVZ", "J", "JBHT", "JCI", "JKHY", "JNJ", "JNPR",
    "JPM", "K", "KDP", "KEY", "KEYS", "KHC", "KIM", "KLAC", "KMB", "KMI",
    "KMX", "KO", "KR", "L", "LDOS", "LEN", "LH", "LHX", "LIN", "LKQ",
    "LLY", "LMT", "LNT", "LOW", "LRCX", "LUV", "LVS", "LW",
    "LYB", "LYV", "MA", "MAA", "MAR", "MAS", "MCD", "MCHP", "MCK", "MCO",
    "MDLZ", "MDT", "MET", "META", "MGM", "MHK", "MKC", "MKTX", "MLM", "MMC",
    "MMM", "MNST", "MO", "MOH", "MOS", "MPC", "MPWR", "MRK", "MRNA", "MRO",
    "MS", "MSCI", "MSFT", "MSI", "MTB", "MTCH", "MTD", "MU", "NCLH", "NDAQ",
    "NDSN", "NEE", "NEM", "NFLX", "NI", "NKE", "NOC", "NOW", "NRG", "NSC",
    "NTAP", "NTRS", "NUE", "NVDA", "NVR", "NWL", "NWS", "NWSA", "NXPI", "O",
    "ODFL", "OGN", "OKE", "OMC", "ON", "ORCL", "ORLY", "OTIS", "OXY", "PARA",
    "PAYC", "PAYX", "PCAR", "PCG", "PEAK", "PEG", "PEP", "PFE", "PFG", "PG",
    "PGR", "PH", "PHM", "PKG", "PKI", "PLD", "PM", "PNC", "PNR", "PNW",
    "POOL", "PPG", "PPL", "PRU", "PSA", "PSX", "PTC", "PVH", "PWR",
    "PYPL", "QCOM", "QRVO", "RCL", "RE", "REG", "REGN", "RF", "RHI", "RJF",
    "RL", "RMD", "ROK", "ROL", "ROP", "ROST", "RSG", "RTX", "SBAC",
    "SBUX", "SCHW", "SEE", "SHW", "SJM", "SLB", "SNA", "SNPS", "SO",
    "SPG", "SPGI", "SRE", "STE", "STT", "STX", "STZ", "SWK", "SWKS", "SYF",
    "SYK", "SYY", "T", "TAP", "TDG", "TDY", "TECH", "TEL", "TER", "TFC",
    "TFX", "TGT", "TMO", "TMUS", "TPR", "TRGP", "TRMB", "TROW", "TRV", "TSCO",
    "TSLA", "TSN", "TT", "TTWO", "TXN", "TXT", "TYL", "UAL", "UDR", "UHS",
    "ULTA", "UNH", "UNP", "UPS", "URI", "USB", "V", "VFC", "VICI", "VLO",
    "VMC", "VNO", "VRSK", "VRSN", "VRTX", "VTR", "VTRS", "VZ", "WAB", "WAT",
    "WBA", "WBD", "WDC", "WEC", "WELL", "WFC", "WHR", "WM", "WMB", "WMT",
    "WRB", "WRK", "WST", "WTW", "WY", "WYNN", "XEL", "XOM", "XRAY", "XYL",
    "YUM", "ZBH", "ZBRA", "ZION", "ZTS",
]


def _fetch_sp500_from_wikipedia():
    """Scrape current S&P 500 tickers from Wikipedia. Returns list or None."""
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        tables = pd.read_html(url)
        tickers = tables[0]['Symbol'].str.strip().tolist()
        if not (400 <= len(tickers) <= 600):
            logger.warning('Wikipedia returned %d tickers — outside expected range, ignoring', len(tickers))
            return None
        logger.info('Fetched %d S&P 500 tickers from Wikipedia', len(tickers))
        return sorted(tickers)
    except Exception as e:
        logger.warning('Failed to fetch S&P 500 from Wikipedia: %s', e)
        return None


def get_sp500_tickers():
    """Return a list of current S&P 500 ticker symbols.

    Tries Wikipedia first (cached 24h), falls back to a static list.
    """
    global _cached_tickers, _cache_timestamp

    with _cache_lock:
        if _cached_tickers is not None and (time.time() - _cache_timestamp) < _CACHE_TTL:
            return _cached_tickers

    # Fetch outside the lock to avoid blocking other threads
    tickers = _fetch_sp500_from_wikipedia()

    if tickers:
        with _cache_lock:
            _cached_tickers = tickers
            _cache_timestamp = time.time()
        return tickers

    # Fallback — do NOT cache so we retry Wikipedia on next call
    logger.info('Using static fallback ticker list (%d tickers)', len(_FALLBACK_TICKERS))
    return list(_FALLBACK_TICKERS)
