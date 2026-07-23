from pathlib import Path
import json
import sys

base = Path(__file__).resolve().parent
output = base / "output"
required_dirs = [
    output,
    output / "history",
    base / "public",
    base / "logs",
]
missing_dirs = [str(p) for p in required_dirs if not p.exists()]
if missing_dirs:
    print("缺少目录：", missing_dirs)
    sys.exit(2)

status_file = base / "status.json"
if not status_file.exists():
    print("缺少 status.json")
    sys.exit(3)

status = json.loads(status_file.read_text(encoding="utf-8"))
print("status =", status.get("status"))
print("output files:")
for p in sorted(output.rglob("*")):
    if p.is_file():
        print(" -", p.relative_to(base), p.stat().st_size)

if status.get("status") == "success":
    report = output / "mobile_latest.html"
    if not report.exists() or report.stat().st_size < 1000:
        print("报告不存在或过小")
        sys.exit(4)
