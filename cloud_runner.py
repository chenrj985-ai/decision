# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
SITE = BASE / "site"
OUT = BASE / "output"
LOGS = BASE / "logs"

def bj_now():
    return datetime.now(timezone(timedelta(hours=8)))

def run_script(name: str, required: bool) -> int:
    path = BASE / name
    if not path.exists():
        if required:
            raise FileNotFoundError(path)
        return 0
    print(f"[cloud] running {name}", flush=True)
    p = subprocess.run([sys.executable, str(path)], cwd=BASE)
    if required and p.returncode != 0:
        raise RuntimeError(f"{name} failed with code {p.returncode}")
    return p.returncode

def publish_site():
    SITE.mkdir(parents=True, exist_ok=True)
    src = OUT / "mobile_latest.html"
    if not src.exists() or src.stat().st_size < 500:
        raise RuntimeError("output/mobile_latest.html was not generated")
    shutil.copy2(src, SITE / "index.html")

    mapping = {
        "market_snapshot.csv": "market_snapshot.csv",
        "index_snapshot.csv": "index_snapshot.csv",
        "etf_rotation.csv": "etf_rotation.csv",
        "all_scores.csv": "all_scores.csv",
        "buy_candidates.csv": "buy_candidates.csv",
        "position_decisions.csv": "position_decisions.csv",
        "latest_decision.txt": "latest_decision.txt",
    }
    copied = []
    for src_name, dst_name in mapping.items():
        p = OUT / src_name
        if p.exists():
            shutil.copy2(p, SITE / dst_name)
            copied.append(dst_name)

    manifest = {
        "version": "V5.1.1 GitHub core migration",
        "beijing_time": bj_now().strftime("%Y-%m-%d %H:%M:%S"),
        "index": "index.html",
        "files": copied,
        "note": "Original V5.1.1 market/scoring logic preserved; only GitHub orchestration added."
    }
    (SITE / "latest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

def main():
    # Auto-risk is useful but non-fatal: rate limits must not block the market report.
    try:
        run_script("update_risk_data.py", required=False)
    except Exception as e:
        print(f"[cloud] warning: auto risk update skipped: {e}", flush=True)

    run_script("main.py", required=True)
    publish_site()
    print("[cloud] completed: site/index.html", flush=True)

if __name__ == "__main__":
    main()
