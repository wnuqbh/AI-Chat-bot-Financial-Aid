"""Market prices for holdings, via Yahoo Finance (yfinance).

yfinance uses Yahoo's unofficial endpoints: fine for a personal or educational app, but swap in a licensed
market-data API before relying on it commercially. Prices are cached in-process for QUOTES_CACHE_SECONDS.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from flask import current_app

_cache = {}  # symbol -> (fetched_at, quote or None)
_lock = threading.Lock()


def _fetch_quote(symbol):
    import yfinance as yf  # imported lazily: it's slow to import and unused when quotes are disabled

    info = yf.Ticker(symbol).fast_info
    price = info["lastPrice"]
    if price is None:
        return None
    return {
        "price": round(float(price), 4),
        "previous_close": round(float(info["previousClose"]), 4) if info["previousClose"] else None,
        "currency": info["currency"],
    }


def _safe_fetch(symbol):
    try:
        return _fetch_quote(symbol)
    except Exception:
        # Unknown symbols and network failures both land here; the caller just shows no price.
        return None


def get_quotes(symbols):
    """Return {symbol: {"price", "previous_close", "currency"} or None}. Never raises."""
    if not current_app.config["QUOTES_ENABLED"] or not symbols:
        return {}

    ttl = current_app.config["QUOTES_CACHE_SECONDS"]
    now = time.monotonic()
    with _lock:
        result = {s: _cache[s][1] for s in symbols if s in _cache and now - _cache[s][0] < ttl}
    missing = [s for s in symbols if s not in result]

    if missing:
        with ThreadPoolExecutor(max_workers=min(8, len(missing))) as pool:
            fetched = dict(zip(missing, pool.map(_safe_fetch, missing)))
        with _lock:
            for symbol, quote in fetched.items():
                _cache[symbol] = (now, quote)
        result.update(fetched)
    return result


def clear_cache():
    with _lock:
        _cache.clear()
