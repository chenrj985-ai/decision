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
    config
) -> str:
    buys = (
        scored[
            (~scored["held"])
            & scored["signal"].isin([
                "快吃肉候选", "趋势候选", "超跌试仓"
            ])
        ].head(int(config["recommend_max"]))
        if not scored.empty else pd.DataFrame()
    )
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
    </style>
    """

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>V6腾讯行情决策系统</title>
{css}
</head>
<body>
<div class="wrap">
<div class="hero">
  <h1>V6 腾讯主源 · 市场风险 + ETF轮动 + 爆雷拦截</h1>
  <div class="note">生成时间：{now:%Y-%m-%d %H:%M:%S}</div>
  <div class="grid">
    <div class="card"><div>市场模式</div><div class="big {mode_class}">{mode}</div></div>
    <div class="card"><div>综合风险</div><div class="big {mode_class}">{risk}/100</div></div>
    <div class="card"><div>建议最高仓位</div><div class="big">{allowed}%</div></div>
    <div class="card"><div>今日正式候选</div><div class="big">{len(buys)}只</div></div>
  </div>
  <div class="note">{summary}</div>
  <div class="note">国际事件：{notes}</div>
  <div class="note">数据源：{source_note}</div>
</div>

<h2>今日允许关注</h2>
<div class="scroll">{html_table(buys, [
    'signal','code','name','sector','price','pct',
    'etf_name','etf_grade','etf_score',
    'relative_strength','quick_profit_score',
    'oversold_score','explosion_index','action'
], 10)}</div>

<h2>持仓决策</h2>
<div class="scroll">{html_table(held, [
    'signal','code','name','sector','price','cost',
    'position_pnl','pct','etf_name','etf_grade',
    'relative_strength','explosion_index',
    'explosion_reason','final_score','action'
], 50)}</div>

<h2>爆雷与行业禁买</h2>
<div class="scroll">{html_table(blocked, [
    'signal','code','name','sector','price','pct',
    'etf_grade','explosion_index',
    'explosion_reason','event_note','action'
], 50)}</div>

<h2>行业ETF强弱与生命周期</h2>
<div class="scroll">{html_table(etfs, [
    'name','price','pct','etf_score','grade','breadth',
    'relative_strength','drawdown_from_recent_peak','alert'
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
<div class="scroll">{html_table(scored, [
    'signal','code','name','sector','source','price','pct',
    'etf_grade','etf_score','relative_strength','quality_score',
    'quick_profit_score','oversold_score','explosion_index',
    'final_score','action'
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
