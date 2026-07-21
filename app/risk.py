from __future__ import annotations

import math
from datetime import datetime
from statistics import mean
from typing import Dict, List, Tuple

import pandas as pd

from .paths import HISTORY, GLOBAL_AUTO, GLOBAL_MANUAL
from .utils import clamp, read_csv_any, safe_float


def load_etf_history() -> pd.DataFrame:
    files = sorted(HISTORY.glob("etf_*.csv"))[-20:]
    frames = []
    for path in files:
        try:
            df = read_csv_any(path)
            if not df.empty:
                df["date"] = path.stem.replace("etf_", "")[:8]
                frames.append(df)
        except Exception:
            pass
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def score_etfs(
    etf_df: pd.DataFrame,
    stock_df: pd.DataFrame,
    config: dict
) -> pd.DataFrame:
    if etf_df.empty:
        return etf_df

    history = load_etf_history()
    reverse: Dict[str, List[str]] = {}
    for sector, etf_name in config["sector_etf_map"].items():
        reverse.setdefault(etf_name, []).append(sector)

    rows = []
    for _, row in etf_df.iterrows():
        name = row["name"]
        hist = (
            history[history["name"] == name].copy()
            if not history.empty and "name" in history.columns
            else pd.DataFrame()
        )
        past = list(hist["price"].map(safe_float))[-10:] if not hist.empty else []
        peak = max(past + [row["price"]]) if past else row["high"] or row["price"]
        drawdown = (row["price"] / peak - 1) * 100 if peak else 0

        trend = 50 + row["pct"] * 5 + (row["close_location"] - 0.5) * 30
        if len(past) >= 3:
            trend += 10 if row["price"] >= mean(past[-3:]) else -10
        if len(past) >= 8:
            trend += 12 if row["price"] >= mean(past[-8:]) else -12

        sectors = reverse.get(name, [])
        subset = (
            stock_df[stock_df["sector"].isin(sectors)]
            if sectors else pd.DataFrame()
        )
        breadth = (subset["pct"] > 0).mean() * 100 if not subset.empty else 50
        median_pct = subset["pct"].median() if not subset.empty else row["pct"]
        relative = row["pct"] - etf_df["pct"].median()

        score = clamp(
            trend * 0.42
            + breadth * 0.28
            + clamp(50 + relative * 8) * 0.18
            + clamp(50 + median_pct * 6) * 0.12
        )
        grade = (
            "S" if score >= 82 else
            "A" if score >= 70 else
            "B" if score >= 58 else
            "C" if score >= 45 else
            "D" if score >= 30 else "E"
        )

        alert = "正常"
        abs_dd = abs(min(0, drawdown))
        if (
            abs_dd >= config["industry_alert_drawdown_red"]
            or (grade == "E" and row["pct"] <= -3)
        ):
            alert = "红色：行业共振回撤，停止新增，反弹优先减弱"
        elif (
            abs_dd >= config["industry_alert_drawdown_orange"]
            or grade == "D"
        ):
            alert = "橙色：趋势破坏，暂停新开仓"
        elif (
            abs_dd >= config["industry_alert_drawdown_yellow"]
            or grade == "C"
        ):
            alert = "黄色：高位降温，停止追高"

        rows.append({
            **row.to_dict(),
            "etf_score": round(score, 2),
            "grade": grade,
            "breadth": round(breadth, 1),
            "median_stock_pct": round(median_pct, 2),
            "relative_strength": round(relative, 2),
            "drawdown_from_recent_peak": round(drawdown, 2),
            "alert": alert
        })

    return pd.DataFrame(rows).sort_values(
        ["etf_score", "pct"], ascending=False
    )


def global_risk_score(config: dict):
    frames = [
        read_csv_any(GLOBAL_AUTO),
        read_csv_any(GLOBAL_MANUAL)
    ]
    frames = [df for df in frames if not df.empty]
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    score = 25.0
    notes = []
    if not df.empty:
        today = datetime.now().date()
        seen = set()
        for _, row in df.iterrows():
            try:
                date = pd.to_datetime(row.get("date"), errors="coerce")
                if pd.isna(date):
                    continue
                age = (today - date.date()).days
                if age < 0 or age > 14:
                    continue

                item = str(row.get("item", "事件")).strip()
                key = "".join(ch for ch in item.lower() if ch.isalnum())[:48]
                if key and key in seen:
                    continue
                seen.add(key)

                impact = safe_float(row.get("impact"))
                direction = str(row.get("direction", "risk")).lower()
                decay = math.exp(-age / 4.0)
                sign = 1 if direction in {
                    "risk", "negative", "-", "利空"
                } else -1
                signed = abs(impact) * decay * sign
                score += signed
                notes.append(f"{item}({signed:+.1f}) {row.get('note', '')}")
            except Exception:
                continue

    return round(clamp(score), 1), notes[:12]


def market_regime(
    index_df: pd.DataFrame,
    stock_df: pd.DataFrame,
    etf_scores: pd.DataFrame,
    global_risk: float,
    config: dict
):
    if stock_df.empty:
        return "数据不足", 100.0, 0, ["股票行情为空"]

    up_ratio = (stock_df["pct"] > 0).mean() * 100
    avg_pct = stock_df["pct"].mean()
    severe_down = (stock_df["pct"] <= -5).mean() * 100
    strong_etf = (
        etf_scores["grade"].isin(["S", "A"]).sum()
        if not etf_scores.empty else 0
    )
    weak_etf = (
        etf_scores["grade"].isin(["D", "E"]).sum()
        if not etf_scores.empty else 0
    )
    index_pct = (
        index_df["pct"].mean()
        if not index_df.empty else avg_pct
    )

    domestic_risk = (
        50
        - (up_ratio - 50) * 0.55
        - avg_pct * 7
        - index_pct * 5
        + severe_down * 0.8
        + weak_etf * 2.5
        - strong_etf * 1.5
    )
    weight = float(config.get("international_weight", 0.15))
    risk = clamp(domestic_risk * (1 - weight) + global_risk * weight)

    if risk >= config["market_extreme_block"]:
        mode = "极端风险日"
    elif risk >= config["market_risk_block"]:
        mode = "风险日"
    elif index_pct > 0.5 and up_ratio > 58 and strong_etf >= 3:
        mode = "强势进攻日"
    elif index_pct > 0 and strong_etf >= 1:
        mode = "普通轮动日"
    elif index_pct > 0 and up_ratio < 55:
        mode = "弱势反弹日"
    else:
        mode = "防守观察日"

    allowed = (
        0 if risk >= config["market_extreme_block"] else
        20 if risk >= config["market_risk_block"] else
        40 if risk >= 55 else
        60 if risk >= 40 else 80
    )
    reasons = [
        f"上涨样本比例 {up_ratio:.1f}%",
        f"样本平均涨跌 {avg_pct:.2f}%",
        f"指数均值 {index_pct:.2f}%",
        f"强ETF {strong_etf}只",
        f"弱ETF {weak_etf}只",
        f"国际事件风险 {global_risk:.1f}"
    ]
    return mode, round(risk, 1), allowed, reasons
