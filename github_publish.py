from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / "output"
HISTORY = BASE / "history"
LATEST_HTML = BASE / "mobile_latest.html"
LATEST_URL = BASE / "latest_url.txt"
LATEST_MANIFEST = BASE / "latest_manifest.json"
STATUS_JSON = BASE / "status.json"

BJ = timezone(timedelta(hours=8))


def run_engine() -> None:
    subprocess.run([sys.executable, "main.py"], cwd=BASE, check=True)


def repo_public_base() -> str:
    override = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if override:
        return override

    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if "/" in repository:
        owner, repo = repository.split("/", 1)
        return f"https://{owner}.github.io/{repo}"
    return ""


def publish() -> None:
    now = datetime.now(BJ)
    stamp = now.strftime("%Y%m%d_%H%M_%S")
    source = OUTPUT / "mobile_latest.html"
    if not source.exists():
        raise FileNotFoundError("output/mobile_latest.html没有生成")

    HISTORY.mkdir(parents=True, exist_ok=True)
    history_name = f"{stamp}.html"
    history_path = HISTORY / history_name

    shutil.copy2(source, history_path)
    shutil.copy2(source, LATEST_HTML)

    base = repo_public_base()
    latest_relative = f"history/{history_name}"
    latest_absolute = f"{base}/{latest_relative}" if base else latest_relative

    manifest = {
        "latest_url": latest_absolute,
        "relative_url": latest_relative,
        "version": stamp,
        "beijing_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "GitHub Actions + Tencent Finance",
        "note": "Use cache-busting query parameter when needed, for example latest_manifest.json?t=timestamp"
    }

    # 保持与用户原GitHub结构一致：latest_url.txt本身也是JSON。
    LATEST_URL.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    LATEST_MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    health_file = OUTPUT / "source_health.json"
    health = {}
    if health_file.exists():
        try:
            health = json.loads(health_file.read_text(encoding="utf-8"))
        except Exception:
            health = {}

    status = {
        "ok": True,
        "generated_at_beijing": manifest["beijing_time"],
        "version": stamp,
        "latest": latest_absolute,
        "quote_source": health.get("source", "腾讯财经"),
        "quote_coverage": health.get("coverage", None),
        "quote_received": health.get("received", None),
        "quote_requested": health.get("requested", None),
        "cache_used": health.get("cache_used", False)
    }
    STATUS_JSON.write_text(
        json.dumps(status, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # 同步常用CSV，便于手机直接查看和后续调试。
    for name in (
        "latest_decision.txt",
        "buy_candidates.csv",
        "position_decisions.csv",
        "etf_rotation.csv",
        "all_scores.csv",
        "market_snapshot.csv",
        "index_snapshot.csv",
        "source_health.json"
    ):
        src = OUTPUT / name
        if src.exists():
            shutil.copy2(src, BASE / name)

    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def main() -> None:
    run_engine()
    publish()


if __name__ == "__main__":
    main()
