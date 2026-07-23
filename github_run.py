from __future__ import annotations

import json
import os
import shutil
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / "output"
OUTPUT_HISTORY = OUTPUT / "history"
PUBLIC = BASE / "public"
PUBLIC_HISTORY = PUBLIC / "history"
ROOT_HISTORY = BASE / "history"
LOGS = BASE / "logs"
BEIJING = timezone(timedelta(hours=8))

PUBLIC_FILES = [
    "latest_decision.txt",
    "buy_candidates.csv",
    "position_decisions.csv",
    "all_scores.csv",
    "etf_rotation.csv",
    "index_snapshot.csv",
    "market_snapshot.csv",
    "source_health.json",
]


def ensure_directories() -> None:
    for folder in (
        OUTPUT, OUTPUT_HISTORY, PUBLIC, PUBLIC_HISTORY,
        ROOT_HISTORY, LOGS
    ):
        folder.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def repo_page_base() -> str:
    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    if "/" not in repo:
        return ""
    owner, repo_name = repo.split("/", 1)
    if repo_name.lower() == f"{owner.lower()}.github.io":
        return f"https://{owner}.github.io"
    return f"https://{owner}.github.io/{repo_name}"


def preserve_previous_public() -> None:
    """
    每次 Actions checkout 后，仓库根目录可能保存着上次成功页面。
    先复制到 public，确保本次行情失败时 Pages 仍能打开旧报告。
    """
    previous = BASE / "mobile_latest.html"
    if previous.exists() and not (PUBLIC / "mobile_latest.html").exists():
        shutil.copy2(previous, PUBLIC / "mobile_latest.html")

    old_history = BASE / "history"
    if old_history.exists():
        for src in old_history.glob("*.html"):
            dst = PUBLIC_HISTORY / src.name
            if not dst.exists():
                shutil.copy2(src, dst)


def publish_success(now: datetime) -> None:
    report = OUTPUT / "mobile_latest.html"
    if not report.exists() or report.stat().st_size < 1000:
        raise RuntimeError(
            "核心程序未生成有效的 output/mobile_latest.html"
        )

    stamp = now.strftime("%Y%m%d_%H%M_%S")
    history_name = f"{stamp}.html"

    # 根目录文件用于兼容用户原有链接
    shutil.copy2(report, BASE / "mobile_latest.html")
    shutil.copy2(report, ROOT_HISTORY / history_name)

    # public 目录是 GitHub Pages 唯一发布源
    shutil.copy2(report, PUBLIC / "mobile_latest.html")
    shutil.copy2(report, PUBLIC_HISTORY / history_name)

    for name in PUBLIC_FILES:
        src = OUTPUT / name
        if src.exists():
            shutil.copy2(src, BASE / name)
            shutil.copy2(src, PUBLIC / name)

    base = repo_page_base()
    latest_url = (
        f"{base}/mobile_latest.html"
        if base else "mobile_latest.html"
    )
    history_url = (
        f"{base}/history/{history_name}"
        if base else f"history/{history_name}"
    )

    manifest = {
        "latest_url": history_url,
        "mobile_latest_url": latest_url,
        "version": stamp,
        "beijing_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "success",
        "note": "Use cache-busting query parameter such as ?t=timestamp"
    }
    status = {
        "status": "success",
        "beijing_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "output_exists": OUTPUT.exists(),
        "report_size": report.stat().st_size,
        "history_file": f"history/{history_name}",
        "github_run_id": os.getenv("GITHUB_RUN_ID", "")
    }

    for base_dir in (BASE, PUBLIC):
        (base_dir / "latest_url.txt").write_text(
            latest_url + "\n", encoding="utf-8"
        )
        write_json(base_dir / "latest_manifest.json", manifest)
        write_json(base_dir / "status.json", status)

    # Pages首页直接跳转最新报告
    index = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="0;url=mobile_latest.html">
<title>V7 Pro 股票决策系统</title>
</head>
<body>
<p>正在打开最新报告……</p>
<p><a href="mobile_latest.html">点击进入最新报告</a></p>
</body>
</html>"""
    (PUBLIC / "index.html").write_text(index, encoding="utf-8")
    (BASE / "index.html").write_text(index, encoding="utf-8")


def publish_failure(now: datetime, detail: str) -> None:
    status = {
        "status": "failed",
        "beijing_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "output_exists": OUTPUT.exists(),
        "output_files": sorted(
            str(p.relative_to(BASE))
            for p in OUTPUT.rglob("*") if p.is_file()
        ),
        "previous_report_preserved":
            (PUBLIC / "mobile_latest.html").exists(),
        "github_run_id": os.getenv("GITHUB_RUN_ID", ""),
        "error": detail[-5000:]
    }
    write_json(BASE / "status.json", status)
    write_json(PUBLIC / "status.json", status)
    (BASE / "github_last_error.txt").write_text(
        detail, encoding="utf-8"
    )
    (OUTPUT / "github_last_error.txt").write_text(
        detail, encoding="utf-8"
    )

    # 第一次运行就失败时，也生成可打开的诊断首页
    if not (PUBLIC / "index.html").exists():
        safe = detail.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>V7 Pro 运行状态</title></head>
<body style="font-family:Arial,'Microsoft YaHei';padding:24px">
<h1>本次行情运行失败</h1>
<p>output 文件夹已经建立，错误已保存到
<code>output/github_last_error.txt</code>。</p>
<pre style="white-space:pre-wrap">{safe[-5000:]}</pre>
</body></html>"""
        (PUBLIC / "index.html").write_text(html, encoding="utf-8")


def main() -> int:
    ensure_directories()
    preserve_previous_public()
    now = datetime.now(BEIJING)

    # 禁止云端尝试打开浏览器
    os.environ["GITHUB_ACTIONS_MODE"] = "1"
    os.environ["TZ"] = "Asia/Shanghai"

    try:
        from app.pipeline import run
        code = run()
        if code != 0:
            raise RuntimeError(f"核心程序返回退出码：{code}")
        publish_success(now)
        print("V7 Pro GitHub运行和发布成功")
        return 0
    except Exception:
        detail = traceback.format_exc()
        print(detail)
        publish_failure(now, detail)
        return 1


if __name__ == "__main__":
    sys.exit(main())
