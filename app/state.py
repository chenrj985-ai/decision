from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from .paths import DYNAMIC_POOL, RISK_POOL, TRACK
from .utils import read_csv_any, safe_float, write_csv


def update_dynamic_pool(scored: pd.DataFrame, config: dict) -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    if scored.empty:
        return

    candidates = scored[
        (scored["final_score"] >= 65)
        & (~scored["signal"].isin([
            "行业禁买", "禁止买入", "爆雷禁买", "回避"
        ]))
    ].copy().head(int(config["dynamic_pool_max"]))

    new = pd.DataFrame({
        "code": candidates["code"],
        "name": candidates["name"],
        "sector": candidates["sector"],
        "source": candidates["signal"],
        "score": candidates["final_score"],
        "add_date": today,
        "last_seen": today
    })

    old = read_csv_any(DYNAMIC_POOL, dtype=str)
    combined = (
        pd.concat([new, old], ignore_index=True)
        if not old.empty else new
    )
    if not combined.empty:
        combined = combined.drop_duplicates("code", keep="first")
        write_csv(
            combined.head(int(config["dynamic_pool_max"])),
            DYNAMIC_POOL
        )


def update_risk_pool(
    scored: pd.DataFrame,
    etfs: pd.DataFrame,
    config: dict
) -> None:
    today = datetime.now().date()
    rows = []
    alert_map = (
        etfs.set_index("name")["alert"].to_dict()
        if not etfs.empty else {}
    )

    if not scored.empty:
        for _, row in scored.iterrows():
            if row["signal"] in {
                "持仓减法", "持仓风险", "行业禁买",
                "禁止买入", "爆雷禁买"
            }:
                level = (
                    "红" if row["signal"] in {"禁止买入", "爆雷禁买"}
                    else "橙"
                )
                rows.append({
                    "code": row["code"],
                    "name": row["name"],
                    "sector": row["sector"],
                    "risk_level": level,
                    "reason":
                        row["action"] + "；"
                        + alert_map.get(row["etf_name"], ""),
                    "add_date": str(today),
                    "expire_date": str(
                        today + timedelta(days=int(config["risk_keep_days"]))
                    )
                })

    write_csv(
        pd.DataFrame(rows, columns=[
            "code", "name", "sector", "risk_level",
            "reason", "add_date", "expire_date"
        ]),
        RISK_POOL
    )


def update_tracking(
    scored: pd.DataFrame,
    mode: str,
    config: dict
) -> pd.DataFrame:
    columns = [
        "recommend_time", "code", "name", "sector", "price",
        "signal", "market_mode", "etf_grade", "score",
        "status", "last_price", "max_return", "min_return", "days"
    ]
    history = read_csv_any(TRACK, dtype=str)
    if history.empty:
        history = pd.DataFrame(columns=columns)

    if scored.empty:
        write_csv(history, TRACK)
        return history

    price_map = scored.set_index("code")["price"].to_dict()
    now = datetime.now()

    for index, row in history.iterrows():
        code = str(row["code"]).zfill(6)
        if code not in price_map:
            continue
        start = safe_float(row["price"])
        current = safe_float(price_map[code])
        ret = (current / start - 1) * 100 if start else 0
        history.at[index, "last_price"] = current
        history.at[index, "max_return"] = max(
            safe_float(row.get("max_return"), ret), ret
        )
        history.at[index, "min_return"] = min(
            safe_float(row.get("min_return"), ret), ret
        )
        dt = pd.to_datetime(row["recommend_time"], errors="coerce")
        days = (
            max(0, (now.date() - dt.date()).days)
            if not pd.isna(dt) else 0
        )
        history.at[index, "days"] = days
        if days >= 5 and str(row.get("status", "open")) == "open":
            history.at[index, "status"] = "win" if ret > 0 else "loss"

    existing_open = set(
        history.loc[
            history["status"] == "open", "code"
        ].astype(str).str.zfill(6)
    )
    selected = scored[
        (~scored["held"])
        & scored["signal"].isin([
            "快吃肉候选", "趋势候选", "超跌试仓"
        ])
    ].head(int(config["recommend_max"]))

    new_rows = []
    for _, row in selected.iterrows():
        if row["code"] in existing_open:
            continue
        new_rows.append({
            "recommend_time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "code": row["code"],
            "name": row["name"],
            "sector": row["sector"],
            "price": row["price"],
            "signal": row["signal"],
            "market_mode": mode,
            "etf_grade": row["etf_grade"],
            "score": row["final_score"],
            "status": "open",
            "last_price": row["price"],
            "max_return": 0,
            "min_return": 0,
            "days": 0
        })

    if new_rows:
        history = pd.concat(
            [pd.DataFrame(new_rows), history],
            ignore_index=True
        )
    write_csv(history, TRACK)
    return history
