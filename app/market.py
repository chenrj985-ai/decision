from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Dict

import pandas as pd
import yfinance as yf


@dataclass
class Quote:
    symbol: str
    last: float | None
    change_pct: float | None
    ma20_gap_pct: float | None
    volume_ratio: float | None
    status: str

    def to_dict(self):
        return asdict(self)


def _safe_float(x):
    try:
        x = float(x)
        return None if math.isnan(x) else x
    except Exception:
        return None


def fetch_quote(symbol: str, period: str = "6mo") -> Quote:
    try:
        df = yf.download(symbol, period=period, interval="1d", auto_adjust=False, progress=False, threads=False)
        if df is None or df.empty:
            return Quote(symbol, None, None, None, None, "no_data")
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        close = df["Close"].dropna()
        vol = df["Volume"].dropna() if "Volume" in df.columns else pd.Series(dtype=float)
        if len(close) < 2:
            return Quote(symbol, _safe_float(close.iloc[-1]), None, None, None, "insufficient")
        last = _safe_float(close.iloc[-1])
        prev = _safe_float(close.iloc[-2])
        chg = (last / prev - 1) * 100 if last and prev else None
        ma20 = _safe_float(close.tail(20).mean())
        gap = (last / ma20 - 1) * 100 if last and ma20 else None
        vr = None
        if len(vol) >= 6 and _safe_float(vol.tail(5).mean()):
            vr = _safe_float(vol.iloc[-1] / vol.iloc[-6:-1].mean())
        return Quote(symbol, last, chg, gap, vr, "ok")
    except Exception as exc:
        return Quote(symbol, None, None, None, None, f"error:{type(exc).__name__}")


def fetch_many(symbols: Dict[str, str]) -> dict:
    return {name: fetch_quote(symbol).to_dict() for name, symbol in symbols.items()}
