from __future__ import annotations


def clamp(v, lo=0, hi=100):
    return max(lo, min(hi, v))


def global_risk(market: dict, news: dict) -> dict:
    score = 35.0
    reasons = []
    for name, q in market.items():
        chg = q.get("change_pct")
        if chg is None:
            continue
        if name == "VIX":
            if q.get("last") and q["last"] > 25:
                score += 18; reasons.append("VIX偏高")
            elif q.get("last") and q["last"] < 18:
                score -= 6
        elif chg < -2:
            score += 9; reasons.append(f"{name}大跌")
        elif chg < -1:
            score += 4
        elif chg > 1.5:
            score -= 3
    news_risk = max([x.get("risk", 0) for x in news.get("items", [])] or [0])
    score += news_risk * 0.45
    score = round(clamp(score), 1)
    level = "低" if score < 35 else "中" if score < 60 else "高" if score < 80 else "极高"
    regime = "进攻" if score < 35 else "轮动" if score < 55 else "防守" if score < 75 else "避险"
    return {"score": score, "level": level, "regime": regime, "reasons": reasons[:6]}


def stock_score(q: dict, etf_strength: float, risk_score: float) -> dict:
    score = 50.0
    reasons = []
    chg = q.get("change_pct")
    gap = q.get("ma20_gap_pct")
    vr = q.get("volume_ratio")
    if chg is not None:
        if 0.2 <= chg <= 4.5: score += 9; reasons.append("当日走势健康")
        elif chg > 7: score -= 9; reasons.append("短线涨幅过大")
        elif chg < -5: score -= 12; reasons.append("跌幅偏大")
    if gap is not None:
        if 0 <= gap <= 8: score += 12; reasons.append("位于20日线上方")
        elif gap > 18: score -= 8; reasons.append("偏离均线过远")
        elif gap < -10: score -= 10; reasons.append("趋势偏弱")
    if vr is not None:
        if 1.05 <= vr <= 2.5: score += 7; reasons.append("量能改善")
        elif vr > 4: score -= 3
    score += etf_strength * 0.22
    score -= max(0, risk_score - 50) * 0.28
    score = round(clamp(score), 1)
    action = "闭眼买观察" if score >= 82 else "回撤买" if score >= 70 else "观察" if score >= 55 else "反弹减仓" if score >= 40 else "回避"
    return {"score": score, "action": action, "reasons": reasons[:4]}
