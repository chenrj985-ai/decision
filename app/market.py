from __future__ import annotations

from statistics import mean
from typing import Dict, List, Tuple

import pandas as pd

from .models import Quote
from .utils import safe_float, symbol


def build_quote_frames(
    universe: pd.DataFrame,
    indexes: List[Tuple[str, str]],
    etfs: List[Tuple[str, str]],
    quotes: Dict[str, Quote]
):
    stock_rows = []
    for _, row in universe.iterrows():
        q = quotes.get(symbol(row["code"]))
        if not q or q.price <= 0:
            continue

        stock_rows.append({
            "code": row["code"],
            "name": row["name"] or q.name,
            "sector": row["sector"],
            "source": row["source"],
            "price": q.price,
            "pct": q.pct,
            "open": q.open,
            "high": q.high,
            "low": q.low,
            "pre_close": q.pre_close,
            "amount": q.amount,
            "turnover": q.turnover,
            "volume_ratio": q.volume_ratio,
            "quote_time": q.quote_time,
            "close_location":
                (q.price - q.low) / (q.high - q.low)
                if q.high > q.low else 0.5,
            "high_dist":
                (q.price / q.high - 1) * 100 if q.high else 0,
            "low_rebound":
                (q.price / q.low - 1) * 100 if q.low else 0,
            "price_vs_open":
                (q.price / q.open - 1) * 100 if q.open else 0
        })
    stock_df = pd.DataFrame(stock_rows)

    def simple(pool, kind):
        rows = []
        for sym, name in pool:
            q = quotes.get(sym)
            if not q or q.price <= 0:
                continue
            rows.append({
                "kind": kind,
                "symbol": sym,
                "code": q.code,
                "name": name,
                "price": q.price,
                "pct": q.pct,
                "open": q.open,
                "high": q.high,
                "low": q.low,
                "pre_close": q.pre_close,
                "amount": q.amount,
                "quote_time": q.quote_time,
                "close_location":
                    (q.price - q.low) / (q.high - q.low)
                    if q.high > q.low else 0.5
            })
        return pd.DataFrame(rows)

    return stock_df, simple(indexes, "index"), simple(etfs, "etf")
