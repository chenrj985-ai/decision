from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import List

import pandas as pd

from .paths import OUTPUT, SOURCE_HEALTH


def html_table(df: pd.DataFrame, columns: List[str], limit: int = 30) -> str:
    if df is None or df.empty:
        return '<div class="empty">无</div>'
    use = [c for c in columns if c in df.columns]
    return df[use].head(limit).to_html(
        index=False,
        classes="data",
        border=0,
        escape=True
    )


def render_html(
    now,
    mode,
    risk,
    allowed,
    reasons,
    global_notes,
    index_df,
    etfs,
    scored,
    tracking,
    config,
    dimensions=None,
    human_view=None
) -> str:
    human_view = human_view or {}
    dimensions = dimensions or {}

    # 统一网页最终结论：
    # A/B/C/D 与底部“结论”必须来自同一套交易教练结果，
    # 不再显示旧版原始 signal，避免“A级但写回避”的矛盾。
    scored = scored.copy()
    if not scored.empty and "candidate_grade" in scored.columns:
        grade_to_decision = {
            "A": "一级候选",
            "B": "二级候选",
            "C": "观察",
            "D": "回避",
        }
        scored["final_decision"] = scored["candidate_grade"].map(
            grade_to_decision
        ).fillna("观察")

        # 持仓不套用候选等级，直接显示持仓动作。
        if "held" in scored.columns:
            held_mask = scored["held"].fillna(False).astype(bool)
            if "action" in scored.columns:
                scored.loc[held_mask, "final_decision"] = (
                    scored.loc[held_mask, "action"]
                    .fillna("持仓观察")
                    .astype(str)
                )
            else:
                scored.loc[held_mask, "final_decision"] = "持仓观察"
    a_list = scored[(~scored["held"]) & (scored["candidate_grade"] == "A")].head(
        int(human_view.get("max_a_candidates", 6))
    ) if not scored.empty else pd.DataFrame()
    b_list = scored[(~scored["held"]) & (scored["candidate_grade"] == "B")].head(
        int(human_view.get("max_b_candidates", 12))
    ) if not scored.empty else pd.DataFrame()
    c_list = scored[(~scored["held"]) & (scored["candidate_grade"] == "C")].head(
        int(human_view.get("max_c_candidates", 20))
    ) if not scored.empty else pd.DataFrame()
    d_list = scored[(~scored["held"]) & (scored["candidate_grade"] == "D")].head(30) if not scored.empty else pd.DataFrame()
    buys = a_list
    held = scored[scored["held"]] if not scored.empty else pd.DataFrame()
    alerts = (
        etfs[etfs["alert"] != "正常"]
        if not etfs.empty else pd.DataFrame()
    )
    blocked = (
        scored[scored["signal"].isin([
            "禁止买入", "爆雷禁买", "行业禁买", "持仓风险", "持仓减法"
        ])]
        if not scored.empty else pd.DataFrame()
    )

    mode_class = (
        "danger" if risk >= config["market_risk_block"]
        else "warn" if risk >= 50 else "ok"
    )
    summary = "；".join(reasons)
    notes = (
        "；".join(global_notes)
        if global_notes
        else "没有录入新的国际事件；当前国际风险使用保守基准"
    )

    try:
        health = json.loads(
            SOURCE_HEALTH.read_text(encoding="utf-8")
        )
        source_note = (
            f"腾讯行情 {health.get('received', 0)}/"
            f"{health.get('requested', 0)}，"
            f"覆盖率{float(health.get('coverage', 0)):.1%}，"
            f"缓存：{'是' if health.get('cache_used') else '否'}"
        )
    except Exception:
        source_note = "行情源健康度未知"

    css = """
    <style>
    body{font-family:-apple-system,BlinkMacSystemFont,'Microsoft YaHei',Arial;
         margin:0;background:#f3f6fa;color:#1f2328}
    .wrap{max-width:1500px;margin:auto;padding:16px}
    .hero,.card{background:#fff;border-radius:14px;padding:16px;
         box-shadow:0 2px 10px #00000012}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
         gap:12px;margin:14px 0}
    .big{font-size:28px;font-weight:700}
    .ok{color:#16794b}.warn{color:#a15c00}.danger{color:#c62828}
    h1{margin:0 0 8px}h2{margin-top:24px}
    .data{border-collapse:collapse;width:100%;background:#fff;font-size:13px}
    .data th{position:sticky;top:0;background:#1769aa;color:#fff;padding:8px}
    .data td{padding:7px;border-bottom:1px solid #e6e8eb;text-align:center}
    .data tr:hover{background:#f4f8ff}
    .empty{background:#fff;padding:18px;border-radius:10px}
    .note{font-size:13px;color:#57606a;margin-top:5px}
    .scroll{overflow-x:auto}
    .risk{border-left:5px solid #c62828}
    .metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px}
    .metric{padding:10px;background:#f7f9fc;border-radius:10px;text-align:center}
    .gradeA{border-left:6px solid #1b8a5a}.gradeB{border-left:6px solid #1769aa}
    .gradeC{border-left:6px solid #b7791f}.gradeD{border-left:6px solid #c62828}
    .human{background:#fff8e8;border:1px solid #efd89c}
    </style>
    """

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>V7.7 多源自动发现防雷决策系统</title>
{css}
</head>
<body>
<div class="wrap">
<div class="hero">
  <h1>V7.7 GitHub · 东方财富/新浪/腾讯多源发现 + 重大消息硬否决</h1>
  <div class="note">生成时间：{now:%Y-%m-%d %H:%M:%S}</div>
  <div class="grid">
    <div class="card"><div>市场模式</div><div class="big {mode_class}">{mode}</div></div>
    <div class="card"><div>综合风险</div><div class="big {mode_class}">{risk}/100</div></div>
    <div class="card"><div>建议最高仓位</div><div class="big">{allowed}%</div></div>
    <div class="card"><div>A级正式候选</div><div class="big">{len(a_list)}只</div></div>
    <div class="card"><div>B级观察候选</div><div class="big">{len(b_list)}只</div></div>
  </div>
  <div class="note">{summary}</div>
  <div class="note">国际事件：{notes}</div>
  <div class="note">数据源：{source_note}</div>
</div>

<h2>市场画像：危险指数低，不等于优质股票一定多</h2>
<div class="card">
  <div class="metrics">
    {''.join(f'<div class="metric"><div>{k}</div><div class="big">{v}</div></div>' for k,v in dimensions.items())}
  </div>
  <div class="note">解释：综合风险衡量“市场会不会出大问题”；候选数量衡量“当前股票池里有多少只同时满足行业、位置、承接和追高约束”。两者不是同一个指标。</div>
</div>

<h2>人工盘面判断</h2>
<div class="card human">
  <div>重点板块：{'、'.join(human_view.get('focus_sectors', [])) or '未设置'}</div>
  <div>回避板块：{'、'.join(human_view.get('avoid_sectors', [])) or '未设置'}</div>
  <div>追高：{'允许' if human_view.get('allow_chase') else '禁止'}；
       超跌试仓：{'允许' if human_view.get('allow_oversold') else '禁止'}；
       偏好：{'回踩确认' if human_view.get('prefer_pullback', True) else '主动进攻'}</div>
  <div class="note">{human_view.get('market_note') or '可双击 EDIT_HUMAN_VIEW.cmd 录入今天的人工盘面判断。'}</div>
</div>

<h2>A级：尾盘确认后可小仓</h2>
<div class="scroll gradeA">{html_table(a_list, [
    'candidate_grade','code','name','sector','price','pct',
    'etf_name','etf_grade','life_stage','coach_score','human_adjust',
    'explosion_index','recommend_reasons','deduct_reasons','coach_action'
], 10)}</div>

<h2>B级：观察，等回踩或次日确认</h2>
<div class="scroll gradeB">{html_table(b_list, [
    'candidate_grade','code','name','sector','price','pct',
    'etf_name','etf_grade','life_stage','coach_score','human_adjust',
    'explosion_index','recommend_reasons','deduct_reasons','coach_action'
], 20)}</div>

<h2>C级：扩大观察池，不立即买</h2>
<div class="scroll gradeC">{html_table(c_list, [
    'candidate_grade','code','name','sector','price','pct',
    'etf_name','etf_grade','life_stage','coach_score',
    'recommend_reasons','deduct_reasons','coach_action'
], 30)}</div>

<h2>D级：强但过热或风险不合格</h2>
<div class="scroll gradeD">{html_table(d_list, [
    'candidate_grade','code','name','sector','price','pct',
    'etf_grade','life_stage','coach_score','explosion_index',
    'deduct_reasons','coach_action'
], 30)}</div>

<h2>A级正式候选（统一最终结论）</h2>
<div class="scroll">{html_table(buys, [
    'final_decision','code','name','sector','price','pct',
    'etf_name','etf_grade','etf_score',
    'relative_strength','quick_profit_score',
    'oversold_score','explosion_index','action'
], 10)}</div>

<h2>持仓决策</h2>
<div class="scroll">{html_table(held, [
    'final_decision','code','name','sector','price','cost',
    'position_pnl','pct','etf_name','etf_grade',
    'relative_strength','explosion_index','candidate_grade','coach_score',
    'recommend_reasons','deduct_reasons','explosion_reason','final_score','action'
], 50)}</div>

<h2>爆雷与行业禁买</h2>
<div class="scroll">{html_table(blocked, [
    'final_decision','code','name','sector','price','pct',
    'etf_grade','explosion_index',
    'explosion_reason','event_note','action'
], 50)}</div>

<h2>行业ETF强弱与生命周期</h2>
<div class="scroll">{html_table(etfs, [
    'name','price','pct','etf_score','grade','breadth',
    'relative_strength','drawdown_from_recent_peak','life_stage','stage_advice','alert'
], 30)}</div>

<h2>指数</h2>
<div class="scroll">{html_table(index_df, [
    'name','price','pct','amount','quote_time'
], 20)}</div>

<h2>推荐跟踪</h2>
<div class="scroll">{html_table(tracking, [
    'recommend_time','code','name','signal','market_mode',
    'etf_grade','score','price','last_price',
    'max_return','min_return','days','status'
], 40)}</div>

<h2>全部评分前80</h2>
<div class="note">最终结论唯一对应候选等级：A=一级候选，B=二级候选，C=观察，D=回避。综合得分仅用于同等级内排序。</div>
<div class="scroll">{html_table(scored, [
    'final_decision','code','name','sector','source','price','pct',
    'etf_grade','etf_score','relative_strength','quality_score',
    'quick_profit_score','oversold_score','explosion_index','candidate_grade',
    'coach_score','human_adjust','recommend_reasons','deduct_reasons','final_score','coach_action'
], 80)}</div>
</div>
</body>
</html>"""


def save_report(html: str, now: datetime) -> Path:
    latest = OUTPUT / "mobile_latest.html"
    latest.write_text(html, encoding="utf-8")
    history = OUTPUT / "history" / f"decision_{now:%Y%m%d_%H%M%S}.html"
    history.write_text(html, encoding="utf-8")
    return latest
