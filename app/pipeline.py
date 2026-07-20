from __future__ import annotations

import json
import os
import webbrowser
from datetime import datetime

import pandas as pd

from .data_loader import (
    load_seed_pool, load_positions, load_market_universe, merge_universe
)
from .market import build_quote_frames
from .paths import OUTPUT, HISTORY, SOURCE_HEALTH
from .providers import fetch_tencent, auto_discover
from .report import render_html, save_report
from .risk import score_etfs, global_risk_score, market_regime
from .scoring import score_stocks
from .state import update_dynamic_pool, update_risk_pool, update_tracking
from .templates import ensure_templates
from .utils import (
    cleanup_old_files, disable_environment_proxy,
    load_config, log, symbol, write_csv
)


def _quote_coverage() -> float:
    try:
        health = json.loads(SOURCE_HEALTH.read_text(encoding="utf-8"))
        return float(health.get("coverage", 0))
    except Exception:
        return 0.0


def run() -> int:
    disable_environment_proxy()
    ensure_templates()
    config = load_config()
    now = datetime.now()

    log("V6 腾讯主源完整工程开始运行")

    seed = load_seed_pool()
    positions = load_positions()
    discovered = auto_discover(config)
    universe = merge_universe(seed, positions, discovered, config)
    indexes, etfs_universe = load_market_universe()

    symbols = (
        [symbol(code) for code in universe["code"]]
        + [item[0] for item in indexes]
        + [item[0] for item in etfs_universe]
    )
    quotes = fetch_tencent(symbols, config)
    stock_df, index_df, etf_df = build_quote_frames(
        universe, indexes, etfs_universe, quotes
    )

    if stock_df.empty:
        raise RuntimeError(
            "未取得任何股票行情。请查看output\\source_health.json和logs\\last_error.txt"
        )

    etf_scores = score_etfs(etf_df, stock_df, config)
    global_risk, global_notes = global_risk_score(config)
    mode, risk, allowed, reasons = market_regime(
        index_df, stock_df, etf_scores, global_risk, config
    )
    coverage = _quote_coverage()

    scored = score_stocks(
        stock_df,
        etf_scores,
        positions,
        mode,
        risk,
        coverage,
        config
    )

    update_dynamic_pool(scored, config)
    update_risk_pool(scored, etf_scores, config)
    tracking = update_tracking(scored, mode, config)

    write_csv(stock_df, OUTPUT / "market_snapshot.csv")
    write_csv(index_df, OUTPUT / "index_snapshot.csv")
    write_csv(etf_scores, OUTPUT / "etf_rotation.csv")
    write_csv(scored, OUTPUT / "all_scores.csv")

    buys = (
        scored[
            (~scored["held"])
            & scored["signal"].isin([
                "快吃肉候选", "趋势候选", "超跌试仓"
            ])
        ].head(int(config["recommend_max"]))
        if not scored.empty else pd.DataFrame()
    )
    write_csv(buys, OUTPUT / "buy_candidates.csv")
    write_csv(
        scored[scored["held"]] if not scored.empty else pd.DataFrame(),
        OUTPUT / "position_decisions.csv"
    )

    write_csv(etf_df, HISTORY / f"etf_{now:%Y%m%d}.csv")
    write_csv(scored, HISTORY / f"scores_{now:%Y%m%d_%H%M%S}.csv")

    html = render_html(
        now, mode, risk, allowed, reasons, global_notes,
        index_df, etf_scores, scored, tracking, config
    )
    latest = save_report(html, now)

    lines = [
        f"生成时间：{now:%Y-%m-%d %H:%M:%S}",
        f"市场模式：{mode}",
        f"风险：{risk}/100",
        f"建议最高仓位：{allowed}%",
        f"行情覆盖率：{coverage:.1%}",
        "",
        "【新开仓】"
    ]
    if buys.empty:
        lines.append("无")
    else:
        for _, row in buys.iterrows():
            lines.append(
                f"{row['name']}｜{row['signal']}｜ETF {row['etf_grade']}｜"
                f"分数{row['final_score']}｜爆雷{row['explosion_index']}｜"
                f"{row['action']}"
            )

    lines += ["", "【持仓】"]
    held = scored[scored["held"]] if not scored.empty else pd.DataFrame()
    if held.empty:
        lines.append("无")
    else:
        for _, row in held.iterrows():
            lines.append(
                f"{row['name']}｜盈亏{row['position_pnl']:.2f}%｜"
                f"{row['signal']}｜爆雷{row['explosion_index']}｜{row['action']}"
            )

    (OUTPUT / "latest_decision.txt").write_text(
        "\n".join(lines), encoding="utf-8-sig"
    )

    cleanup_old_files(HISTORY, int(config["history_keep_days"]))
    log(f"运行完成：{latest}")

    if config.get("auto_open_html", True) and not os.environ.get("GITHUB_ACTIONS"):
        try:
            webbrowser.open(latest.as_uri())
        except Exception:
            pass
    return 0
