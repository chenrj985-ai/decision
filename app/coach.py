from __future__ import annotations

import json
from pathlib import Path
import pandas as pd

from .utils import clamp, safe_float

BASE = Path(__file__).resolve().parent.parent
HUMAN_FILE = BASE / "config" / "human_view.json"


def load_human_view() -> dict:
    default = {
        "enabled": True, "manual_weight": 0.18,
        "focus_sectors": [], "avoid_sectors": [],
        "sector_adjustments": {}, "stock_adjustments": {},
        "allow_chase": False, "allow_oversold": False,
        "prefer_pullback": True, "market_note": "",
        "max_a_candidates": 6, "max_b_candidates": 12,
        "max_c_candidates": 20
    }
    try:
        data = json.loads(HUMAN_FILE.read_text(encoding="utf-8"))
        default.update(data)
    except Exception:
        pass
    return default


def market_dimensions(index_df: pd.DataFrame, stock_df: pd.DataFrame,
                      etfs: pd.DataFrame, risk: float) -> dict:
    if stock_df is None or stock_df.empty:
        return {
            "赚钱效应": 0, "市场情绪": 0, "资金承接": 0,
            "板块扩散": 0, "热点持续": 0, "追高安全": 0
        }

    pct = pd.to_numeric(stock_df["pct"], errors="coerce").fillna(0)
    close_loc = pd.to_numeric(
        stock_df.get("close_location", 0.5), errors="coerce"
    ).fillna(0.5)
    pvo = pd.to_numeric(
        stock_df.get("price_vs_open", 0), errors="coerce"
    ).fillna(0)
    vr = pd.to_numeric(
        stock_df.get("volume_ratio", 1), errors="coerce"
    ).fillna(1)

    profit = clamp((pct.gt(0).mean() * 65) + (pct.gt(3).mean() * 90))
    emotion = clamp(50 + pct.median() * 10 + (pct.gt(5).mean() * 80))
    support = clamp(close_loc.mean() * 70 + pvo.gt(0).mean() * 30)
    chase_safe = clamp(100 - risk - pct.gt(7).mean() * 120 - vr.gt(4).mean() * 80)

    if etfs is not None and not etfs.empty:
        esc = pd.to_numeric(etfs["etf_score"], errors="coerce").fillna(50)
        breadth = pd.to_numeric(etfs.get("breadth", 50), errors="coerce").fillna(50)
        spread = clamp(esc.ge(60).mean() * 100)
        persistence = clamp(esc.nlargest(min(5, len(esc))).mean())
        spread = clamp((spread + breadth.mean()) / 2)
    else:
        spread, persistence = 0, 0

    return {
        "赚钱效应": round(profit, 1),
        "市场情绪": round(emotion, 1),
        "资金承接": round(support, 1),
        "板块扩散": round(spread, 1),
        "热点持续": round(persistence, 1),
        "追高安全": round(chase_safe, 1)
    }


def add_sector_lifecycle(etfs: pd.DataFrame) -> pd.DataFrame:
    if etfs is None or etfs.empty:
        return etfs
    out = etfs.copy()
    stages, advice = [], []
    for _, r in out.iterrows():
        score = safe_float(r.get("etf_score"), 50)
        pct = safe_float(r.get("pct"), 0)
        breadth = safe_float(r.get("breadth"), 50)
        drawdown = safe_float(r.get("drawdown_from_recent_peak"), 0)

        if score >= 78 and pct >= 2.5 and breadth >= 70:
            stage, act = "高潮", "强但不宜追高，等分歧回踩"
        elif score >= 68 and pct >= 0.8 and breadth >= 55:
            stage, act = "发酵", "主线候选，优先选未大涨个股"
        elif score >= 58 and pct > 0 and breadth >= 45:
            stage, act = "启动", "可观察，等待持续性确认"
        elif score >= 52 and drawdown > -3:
            stage, act = "分歧", "只留强股，弱股减法"
        elif score < 43 or pct <= -2:
            stage, act = "退潮", "停止新增，反弹处理弱股"
        else:
            stage, act = "震荡", "等待方向，不强行交易"
        stages.append(stage)
        advice.append(act)
    out["life_stage"] = stages
    out["stage_advice"] = advice
    return out


def _reason_penalty(row) -> tuple[list[str], list[str]]:
    reasons, penalties = [], []
    if str(row.get("etf_grade", "")) in {"S", "A"}:
        reasons.append("所属ETF强")
    if safe_float(row.get("relative_strength")) >= 1.2:
        reasons.append("明显强于行业")
    if safe_float(row.get("close_location"), 0.5) >= 0.72:
        reasons.append("价格接近日内强势区")
    if 0.8 <= safe_float(row.get("volume_ratio"), 1) <= 2.5:
        reasons.append("量能较健康")
    if safe_float(row.get("price_vs_open")) > 0:
        reasons.append("开盘后仍有承接")
    if safe_float(row.get("pct")) < 4.5:
        reasons.append("当日未明显追高")
    if safe_float(row.get("quality_score")) >= 62:
        reasons.append("基础质量得分较好")

    pct = safe_float(row.get("pct"))
    if pct >= 7:
        penalties.append("当日涨幅过大")
    elif pct >= 5:
        penalties.append("接近追高区")
    if safe_float(row.get("explosion_index")) >= 45:
        penalties.append("爆雷指数偏高")
    if safe_float(row.get("volume_ratio")) >= 4:
        penalties.append("量比过热")
    if safe_float(row.get("close_location"), .5) < .35 and pct > 0:
        penalties.append("冲高回落")
    if safe_float(row.get("relative_strength")) < -1:
        penalties.append("弱于行业")
    if str(row.get("etf_grade", "")) in {"D", "E"}:
        penalties.append("所属行业偏弱")
    return reasons, penalties


def apply_trading_coach(scored: pd.DataFrame, etfs: pd.DataFrame,
                        risk: float, mode: str, config: dict):
    if scored is None or scored.empty:
        return scored, {}, load_human_view()

    human = load_human_view()
    etf_stage = {}
    if etfs is not None and not etfs.empty and "life_stage" in etfs.columns:
        etf_stage = etfs.set_index("name")["life_stage"].to_dict()

    out = scored.copy()
    coach_scores, grades, reasons_text, penalties_text = [], [], [], []
    human_adjusts, coach_actions = [], []

    focus = set(human.get("focus_sectors", []))
    avoid = set(human.get("avoid_sectors", []))
    sector_adj = human.get("sector_adjustments", {})
    stock_adj = human.get("stock_adjustments", {})
    manual_weight = max(0, min(float(human.get("manual_weight", .18)), .35))

    for _, r in out.iterrows():
        base = safe_float(r.get("final_score"), 0)
        sector = str(r.get("sector", ""))
        code = str(r.get("code", ""))
        pct = safe_float(r.get("pct"))
        explosion = safe_float(r.get("explosion_index"))
        stage = etf_stage.get(str(r.get("etf_name", "")), "未知")

        adjust = safe_float(sector_adj.get(sector), 0)
        adjust += safe_float(stock_adj.get(code), 0)
        if sector in focus:
            adjust += 8
        if sector in avoid:
            adjust -= 18

        # 人工调整最多影响约18分，避免主观完全覆盖硬风险。
        adjust = max(-25, min(adjust, 25))
        score = base * (1 - manual_weight) + clamp(base + adjust) * manual_weight

        reasons, penalties = _reason_penalty(r)
        if stage == "发酵":
            score += 4
            reasons.append("板块处于发酵阶段")
        elif stage == "启动":
            score += 2
            reasons.append("板块处于启动阶段")
        elif stage == "高潮":
            score -= 6
            penalties.append("板块可能处于高潮")
        elif stage == "退潮":
            score -= 14
            penalties.append("板块处于退潮阶段")

        if risk >= 68:
            score -= 12
            penalties.append("市场风险较高")
        elif risk <= 35:
            score += 3
            reasons.append("市场总体风险较低")

        if pct >= 5 and not human.get("allow_chase", False):
            score -= 10
            penalties.append("人工设置禁止追高")
        if str(r.get("signal", "")) == "超跌试仓" and not human.get("allow_oversold", False):
            score -= 10
            penalties.append("人工设置禁止抄底")
        if explosion >= float(config.get("explosion_block", 60)):
            score = min(score, 39)
        if str(r.get("signal", "")) in {"禁止买入", "爆雷禁买", "行业禁买"}:
            score = min(score, 35)

        score = round(clamp(score), 2)

        # 四层候选树：不是只显示三只。
        held = bool(r.get("held", False))
        hard_block = str(r.get("signal", "")) in {
            "禁止买入", "爆雷禁买", "行业禁买", "数据不足观察"
        }
        if held:
            grade = "持仓"
            action = str(r.get("action", "持仓观察"))
        elif hard_block or score < 48:
            grade = "D"
            action = "禁止追入/暂时回避"
        elif score >= 78 and risk < 60 and explosion < 45 and pct < 6:
            grade = "A"
            action = "一级候选：尾盘确认后小仓，禁止急拉追买"
        elif score >= 66 and explosion < 55:
            grade = "B"
            action = "二级观察：等待回踩或次日确认"
        else:
            grade = "C"
            action = "回踩候选：当前不买，进入观察池"

        coach_scores.append(score)
        grades.append(grade)
        reasons_text.append("；".join(reasons[:6]) or "暂无突出加分项")
        penalties_text.append("；".join(penalties[:6]) or "无明显额外扣分")
        human_adjusts.append(round(adjust, 1))
        coach_actions.append(action)

    out["life_stage"] = out["etf_name"].map(etf_stage).fillna("未知")
    out["coach_score"] = coach_scores
    out["candidate_grade"] = grades
    out["recommend_reasons"] = reasons_text
    out["deduct_reasons"] = penalties_text
    out["human_adjust"] = human_adjusts
    out["coach_action"] = coach_actions

    order = {"A": 5, "B": 4, "C": 3, "持仓": 2, "D": 1}
    out["coach_priority"] = out["candidate_grade"].map(order).fillna(0)
    out = out.sort_values(
        ["coach_priority", "coach_score", "final_score"],
        ascending=False
    )
    dimensions = {}
    return out, dimensions, human
