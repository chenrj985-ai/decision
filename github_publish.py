from __future__ import annotations

import json
import os
import shutil
import sys
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / "output"
PUBLIC_HISTORY = BASE / "history"
BEIJING = timezone(timedelta(hours=8))


def page_base_url() -> str:
    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    if "/" not in repo:
        return ""
    owner, name = repo.split("/", 1)
    if name.lower() == f"{owner.lower()}.github.io":
        return f"https://{owner}.github.io"
    return f"https://{owner}.github.io/{name}"


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def publish_success(now: datetime) -> None:
    source = OUTPUT / "mobile_latest.html"
    if not source.exists():
        raise FileNotFoundError("程序运行完成，但 output/mobile_latest.html 不存在")

    PUBLIC_HISTORY.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%d_%H%M_%S")
    history_name = f"{stamp}.html"
    latest = BASE / "mobile_latest.html"
    history_file = PUBLIC_HISTORY / history_name
    shutil.copy2(source, latest)
    shutil.copy2(source, history_file)

    # 同步常用结果，便于手机或外部程序读取
    for name in [
        "latest_decision.txt", "buy_candidates.csv", "position_decisions.csv",
        "all_scores.csv", "etf_rotation.csv", "index_snapshot.csv",
        "market_snapshot.csv", "source_health.json"
    ]:
        src = OUTPUT / name
        if src.exists():
            shutil.copy2(src, BASE / name)

    base = page_base_url()
    latest_url = f"{base}/mobile_latest.html" if base else "mobile_latest.html"
    history_url = f"{base}/history/{history_name}" if base else f"history/{history_name}"

    (BASE / "latest_url.txt").write_text(latest_url + "\n", encoding="utf-8")
    write_json(BASE / "latest_manifest.json", {
        "latest_url": history_url,
        "mobile_latest_url": latest_url,
        "version": stamp,
        "beijing_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "success",
        "note": "Use cache-busting query parameter when necessary, e.g. ?t=timestamp"
    })
    write_json(BASE / "status.json", {
        "status": "success",
        "beijing_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "history_file": f"history/{history_name}",
        "github_run_id": os.getenv("GITHUB_RUN_ID", "")
    })


def publish_failure(now: datetime, detail: str) -> None:
    # 不覆盖上一次成功生成的 mobile_latest.html，只更新状态。
    write_json(BASE / "status.json", {
        "status": "failed",
        "beijing_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "error": detail[-3000:],
        "previous_report_preserved": (BASE / "mobile_latest.html").exists(),
        "github_run_id": os.getenv("GITHUB_RUN_ID", "")
    })
    (BASE / "github_last_error.txt").write_text(detail, encoding="utf-8")


def main() -> int:
    now = datetime.now(BEIJING)
    os.environ["GITHUB_ACTIONS_MODE"] = "1"
    try:
        from app.pipeline import run
        code = run()
        if code != 0:
            raise RuntimeError(f"核心程序返回退出码 {code}")
        publish_success(now)
        print("GitHub发布完成")
        return 0
    except Exception:
        detail = traceback.format_exc()
        print(detail)
        publish_failure(now, detail)
        return 1


if __name__ == "__main__":
    sys.exit(main())
