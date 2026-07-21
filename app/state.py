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
    """
    推荐历史采用“字典记录重建”方式更新。

    原因：
    pandas 3.x 中 dtype=str 可能生成严格 StringDtype。
    即使尝试转换部分列，第二次运行时仍可能在字符串列中写入
    浮点价格并报：
    Invalid value 'xx.xx' for dtype 'str'

    本函数不再对读取后的 DataFrame 原地赋值，而是：
    1. 将旧记录转成普通 Python dict；
    2. 在 dict 中更新价格和收益；
    3. 最后重新创建全新的 DataFrame。
    因而兼容 pandas 2.x 和 3.x。
    """
    columns = [
        "recommend_time", "code", "name", "sector", "price",
        "signal", "market_mode", "etf_grade", "score",
        "status", "last_price", "max_return", "min_return", "days"
    ]

    raw = read_csv_any(TRACK, dtype=str)
    records = []

    if not raw.empty:
        for item in raw.to_dict("records"):
            code = (
                str(item.get("code", ""))
                .replace(".0", "")
                .strip()
                .zfill(6)
            )
            records.append({
                "recommend_time": str(item.get("recommend_time", "")),
                "code": code,
                "name": str(item.get("name", "")),
                "sector": str(item.get("sector", "")),
                "price": safe_float(item.get("price")),
                "signal": str(item.get("signal", "")),
                "market_mode": str(item.get("market_mode", "")),
                "etf_grade": str(item.get("etf_grade", "")),
                "score": safe_float(item.get("score")),
                "status": str(item.get("status", "open")) or "open",
                "last_price": safe_float(item.get("last_price")),
                "max_return": safe_float(item.get("max_return")),
                "min_return": safe_float(item.get("min_return")),
                "days": int(safe_float(item.get("days")))
            })

    if scored is None or scored.empty:
        history = pd.DataFrame.from_records(records, columns=columns)
        write_csv(history, TRACK)
        return history

    price_map = {
        str(code).zfill(6): safe_float(price)
        for code, price in scored.set_index("code")["price"].to_dict().items()
    }
    now = datetime.now()

    updated_records = []
    for rec in records:
        code = str(rec.get("code", "")).zfill(6)
        current = price_map.get(code, 0.0)
        start_price = safe_float(rec.get("price"))

        if current > 0:
            ret = (
                (current / start_price - 1) * 100
                if start_price > 0 else 0.0
            )
            rec["last_price"] = round(current, 4)
            rec["max_return"] = round(
                max(safe_float(rec.get("max_return"), ret), ret), 4
            )
            rec["min_return"] = round(
                min(safe_float(rec.get("min_return"), ret), ret), 4
            )

            dt = pd.to_datetime(
                rec.get("recommend_time", ""),
                errors="coerce"
            )
            days = (
                max(0, (now.date() - dt.date()).days)
                if not pd.isna(dt) else 0
            )
            rec["days"] = int(days)

            if (
                days >= 5
                and str(rec.get("status", "open")) == "open"
            ):
                rec["status"] = "win" if ret > 0 else "loss"

        updated_records.append(rec)

    existing_open = {
        str(rec.get("code", "")).zfill(6)
        for rec in updated_records
        if str(rec.get("status", "open")) == "open"
    }

    # V7 Pro 使用交易教练后的 A/B 候选写入推荐历史。
    if "candidate_grade" in scored.columns:
        selected = scored[
            (~scored["held"])
            & scored["candidate_grade"].isin(["A", "B"])
        ].head(int(config.get("recommend_max", 18)))
    else:
        selected = scored[
            (~scored["held"])
            & scored["signal"].isin([
                "快吃肉候选", "趋势候选", "超跌试仓"
            ])
        ].head(int(config.get("recommend_max", 18)))

    new_records = []
    for _, row in selected.iterrows():
        code = str(row.get("code", "")).zfill(6)
        if not code or code in existing_open:
            continue

        grade = str(row.get("candidate_grade", ""))
        signal = str(row.get("signal", ""))
        if grade:
            signal = f"{grade}级-{signal}"

        price = safe_float(row.get("price"))
        new_records.append({
            "recommend_time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "code": code,
            "name": str(row.get("name", "")),
            "sector": str(row.get("sector", "")),
            "price": round(price, 4),
            "signal": signal,
            "market_mode": str(mode),
            "etf_grade": str(row.get("etf_grade", "")),
            "score": round(
                safe_float(
                    row.get("coach_score", row.get("final_score", 0))
                ), 4
            ),
            "status": "open",
            "last_price": round(price, 4),
            "max_return": 0.0,
            "min_return": 0.0,
            "days": 0
        })

    all_records = new_records + updated_records
    history = pd.DataFrame.from_records(all_records, columns=columns)

    # 显式规定列类型，彻底避免严格字符串列与浮点数冲突。
    numeric_cols = [
        "price", "score", "last_price",
        "max_return", "min_return", "days"
    ]
    for col in numeric_cols:
        history[col] = pd.to_numeric(
            history[col], errors="coerce"
        ).fillna(0)

    for col in [
        "recommend_time", "code", "name", "sector", "signal",
        "market_mode", "etf_grade", "status"
    ]:
        history[col] = history[col].fillna("").astype(object)

    history["code"] = (
        history["code"].astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(6)
    )

    write_csv(history, TRACK)
    return history
