from __future__ import annotations

import math

import pandas as pd

from .events import load_event_map
from .utils import clamp, safe_float


def explosion_index(row, etf_grade: str, event: dict, config: dict):
    score = 0.0
    reasons = []

    pct = safe_float(row.get("pct"))
    turnover = safe_float(row.get("turnover"))
    volume_ratio = safe_float(row.get("volume_ratio"))
    close_location = safe_float(row.get("close_location"), 0.5)
    high_dist = safe_float(row.get("high_dist"))
    price_vs_open = safe_float(row.get("price_vs_open"))

    if event.get("bad"):
        score += 100
        reasons.append("重大明确利空")
    if event.get("risk", 0) > 0:
        score += min(35, event["risk"])
        reasons.append(f"事件风险+{event['risk']:.0f}")

    # 极端下跌必须比追高风险优先处理。
    if pct <= -9.3:
        score += 100
        reasons.append("跌停或接近跌停，禁止新增")
    elif pct <= -7:
        score += 55
        reasons.append("当日跌幅超过7%，禁止抄底")
    elif pct <= -5:
        score += 30
        reasons.append("当日大跌，进入风险观察")

    if pct >= 9.3:
        score += 35
        reasons.append("接近涨停，追高风险")
    elif pct >= 7:
        score += 25
        reasons.append("当日涨幅超过7%")
    elif pct >= config["max_chase_pct"]:
        score += 18
        reasons.append("超过追高阈值")

    if turnover >= 25:
        score += 18
        reasons.append("换手率过高")
    elif turnover >= 15:
        score += 10
        reasons.append("换手率偏高")

    if volume_ratio >= 5:
        score += 18
        reasons.append("量比异常放大")
    elif volume_ratio >= 3.5:
        score += 10
        reasons.append("量比偏高")

    if close_location < 0.25 and pct > 2:
        score += 15
        reasons.append("冲高回落明显")
    if price_vs_open < -2 and pct > 0:
        score += 10
        reasons.append("开盘后显著走弱")
    if high_dist < -4 and pct > 0:
        score += 8
        reasons.append("距日内高点较远")

    if etf_grade == "D":
        score += 20
        reasons.append("所属ETF为D级")
    elif etf_grade == "E":
        score += 35
        reasons.append("所属ETF为E级")

    return round(clamp(score), 1), reasons


def score_stocks(
    stock_df: pd.DataFrame,
    etf_scores: pd.DataFrame,
    positions: pd.DataFrame,
    mode: str,
    market_risk: float,
    quote_coverage: float,
    config: dict
) -> pd.DataFrame:
    etf_map = config["sector_etf_map"]
    etf_lookup = (
        etf_scores.set_index("name").to_dict("index")
        if not etf_scores.empty else {}
    )
    position_map = (
        positions.set_index("code").to_dict("index")
        if not positions.empty else {}
    )
    events = load_event_map()
    rows = []

    strict_data_ok = quote_coverage >= float(config["quote_min_coverage"])

    for _, row in stock_df.iterrows():
        event = events.get(
            row["code"],
            {"bad": False, "risk": 0, "boost": 0, "note": ""}
        )
        etf_name = etf_map.get(row["sector"], "")
        etf = etf_lookup.get(etf_name, {})
        etf_score = safe_float(etf.get("etf_score"), 50)
        etf_grade = str(etf.get("grade", "C"))
        etf_pct = safe_float(etf.get("pct"), 0)
        relative = row["pct"] - etf_pct

        quality = 50
        quality += 14 if row["source"] in {"核心池", "持仓"} else 2
        quality += min(
            10,
            math.log10(max(safe_float(row["amount"]), 1)) * 2 - 8
        )
        quality += event["boost"] - event["risk"]

        trend = (
            48
            + relative * 6
            + (row["close_location"] - 0.5) * 38
            + row["price_vs_open"] * 3
        )
        if 0.75 <= row["volume_ratio"] <= 2.5:
            trend += 10
        elif row["volume_ratio"] > 4:
            trend -= 5
        if row["high_dist"] >= -1.8:
            trend += 8
        if row["pct"] >= config["max_chase_pct"]:
            trend -= 18

        quick = trend * 0.46 + etf_score * 0.34 + quality * 0.20
        if mode == "强势进攻日":
            quick += 7
        elif mode == "普通轮动日":
            quick += 2
        elif mode in {"风险日", "极端风险日"}:
            quick -= 20
        elif mode == "弱势反弹日":
            quick -= 8
        quick = clamp(quick)

        oversold = 0.0
        if row["pct"] <= -4.5:
            confirm = (
                row["low_rebound"] >= 2
                and row["close_location"] >= 0.55
                and relative >= -1
            )
            oversold = clamp(
                42
                + abs(row["pct"]) * 3
                + etf_score * 0.18
                + quality * 0.16
                + (18 if confirm else -12)
                - market_risk * 0.12
            )

        held = row["code"] in position_map
        cost = safe_float(position_map.get(row["code"], {}).get("cost"), 0)
        pnl = (row["price"] / cost - 1) * 100 if held and cost else 0

        explosion, explosion_reasons = explosion_index(
            row, etf_grade, event, config
        )

        blocked = (
            event["bad"]
            or etf_grade in {"D", "E"}
            or market_risk >= config["market_extreme_block"]
            or explosion >= config["explosion_block"]
            or not strict_data_ok
        )

        signal = "回避"
        action = "当前无优势"

        if event["bad"]:
            signal = "禁止买入"
            action = "重大利空；若持有，反弹优先退出"
        elif held:
            if etf_grade in {"D", "E"} and relative < 0:
                signal = "持仓减法"
                action = "行业弱且个股更弱；反弹优先减1手"
            elif explosion >= config["explosion_block"]:
                signal = "持仓风险"
                action = "爆雷指数较高；不补仓，反弹时降低仓位"
            elif quick >= config["quick_profit_min_score"] and etf_grade in {"S", "A"}:
                signal = "核心保留"
                action = "相对强，继续持有；不因刚回本机械清仓"
            elif relative < -2 or row["pct"] <= -5:
                signal = "持仓观察"
                action = "暂不补仓；观察反弹质量"
            else:
                signal = "持仓保留"
                action = "继续观察；持续弱于ETF时再降仓"
        elif not strict_data_ok:
            signal = "数据不足观察"
            action = "行情覆盖率不足，本次不允许新开仓"
        elif explosion >= config["explosion_block"]:
            signal = "爆雷禁买"
            action = "爆雷指数超过阈值，禁止追入"
        elif (
            not blocked
            and quick >= config["quick_profit_min_score"]
            and etf_score >= config["etf_buy_min_score"]
        ):
            signal = "快吃肉候选"
            action = "仅小仓1手；尾盘确认且不得急拉追入"
        elif (
            not blocked
            and quick >= config["stock_buy_min_score"]
            and etf_score >= config["etf_buy_min_score"]
        ):
            signal = "趋势候选"
            action = "强ETF中的强股；等待回踩后小仓"
        elif (
            oversold >= config["oversold_min_score"]
            and etf_grade not in {"D", "E"}
            and market_risk < config["market_risk_block"]
        ):
            signal = "超跌试仓"
            action = "仅1手，必须有低位回拉确认"
        elif etf_grade in {"D", "E"}:
            signal = "行业禁买"
            action = f"{etf_name or row['sector']}为{etf_grade}级，停止新增"

        final_score = max(quick, oversold)
        rows.append({
            **row.to_dict(),
            "etf_name": etf_name,
            "etf_grade": etf_grade,
            "etf_score": round(etf_score, 2),
            "relative_strength": round(relative, 2),
            "quality_score": round(clamp(quality), 2),
            "quick_profit_score": round(quick, 2),
            "oversold_score": round(oversold, 2),
            "explosion_index": explosion,
            "explosion_reason": "；".join(explosion_reasons),
            "held": held,
            "cost": cost,
            "position_pnl": round(pnl, 2),
            "event_note": event["note"],
            "signal": signal,
            "action": action,
            "final_score": round(final_score, 2)
        })

    output = pd.DataFrame(rows)
    if output.empty:
        return output

    priority = {
        "快吃肉候选": 10,
        "趋势候选": 9,
        "超跌试仓": 8,
        "核心保留": 7,
        "持仓保留": 6,
        "持仓观察": 5,
        "持仓风险": 4,
        "持仓减法": 3,
        "数据不足观察": 2,
        "行业禁买": 1,
        "爆雷禁买": 0,
        "回避": 0,
        "禁止买入": -1
    }
    output["priority"] = output["signal"].map(priority).fillna(0)
    return output.sort_values(
        ["priority", "final_score"], ascending=False
    )
