from __future__ import annotations
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
BJ = timezone(timedelta(hours=8))
status_path = BASE / "status.json"

old = {}
if status_path.exists():
    try:
        old = json.loads(status_path.read_text(encoding="utf-8"))
    except Exception:
        pass

old.update({
    "ok": False,
    "last_attempt_beijing": datetime.now(BJ).strftime("%Y-%m-%d %H:%M:%S"),
    "message": "本次GitHub Actions取数或生成失败，网站继续保留上一次成功报告。",
    "run_url": (
        f"https://github.com/{os.environ.get('GITHUB_REPOSITORY','')}/actions/runs/"
        f"{os.environ.get('GITHUB_RUN_ID','')}"
    )
})
status_path.write_text(json.dumps(old, ensure_ascii=False, indent=2), encoding="utf-8")
