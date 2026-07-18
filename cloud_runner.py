from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from app.market import fetch_many, fetch_quote
from app.news import fetch_news
from app.report import build_site
from app.scoring import global_risk, stock_score
from app.utils import ROOT, atomic_write, ensure_dirs, load_json, now_cn, save_json


def read_csv(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def suffix(code: str) -> str:
    code = str(code).zfill(6)
    return f"{code}.SS" if code.startswith(("6", "9")) else f"{code}.SZ"


def main() -> int:
    ensure_dirs()
    cfg = load_json(ROOT / "config/settings.json", {}) or {}
    market = fetch_many(cfg.get("market_symbols", {}))
    etfs = fetch_many(cfg.get("etfs", {}))
    news = fetch_news(cfg.get("network_timeout_seconds", 15), cfg.get("news_cache_hours", 6))
    risk = global_risk(market, news)

    etf_strength = {}
    for name, q in etfs.items():
        etf_strength[name] = (q.get("change_pct") or 0) * 4 + (q.get("ma20_gap_pct") or 0) * 1.2

    stocks = []
    for row in read_csv(ROOT / "data/stock_pool_seed.csv"):
        q = fetch_quote(suffix(row["code"])).to_dict()
        industry = row.get("industry", "")
        strength = max(etf_strength.values() or [0])
        for etf_name, value in etf_strength.items():
            if etf_name in industry or industry in etf_name:
                strength = value
                break
        decision = stock_score(q, strength, risk["score"])
        stocks.append({**row, "quote": q, "decision": decision})
    stocks.sort(key=lambda x: x["decision"]["score"], reverse=True)
    stocks = stocks[: int(cfg.get("top_recommendations", 12))]

    snapshot = {
        "version": "6.0.1-formal",
        "generated_at": now_cn().strftime("%Y-%m-%d %H:%M:%S"),
        "market": market,
        "etfs": etfs,
        "news": news,
        "risk": risk,
        "stocks": stocks,
        "health": {
            "stocks_ok": sum(x["quote"]["status"] == "ok" for x in stocks),
            "stocks_total": len(stocks),
            "etfs_ok": sum(x.get("status") == "ok" for x in etfs.values()),
            "etfs_total": len(etfs),
        },
    }

    stamp = now_cn().strftime("%Y%m%d_%H%M%S")
    save_json(ROOT / "output/latest.json", snapshot)
    save_json(ROOT / f"output/history/{stamp}.json", snapshot)
    build_site(snapshot)
    atomic_write(ROOT / "logs/latest.log", f"{snapshot['generated_at']} run_ok risk={risk['score']} stocks={len(stocks)}\n")
    atomic_write(ROOT / "reports/latest_summary.txt", f"风险={risk['score']} {risk['level']} {risk['regime']}\n推荐={','.join(x['name'] for x in stocks[:5])}\n")
    print(json.dumps(snapshot["health"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
