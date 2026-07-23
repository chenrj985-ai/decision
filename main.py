from __future__ import annotations

import sys
import traceback

from app.paths import LOGS
from app.pipeline import run
from app.utils import log


def main() -> None:
    try:
        code = run()
    except KeyboardInterrupt:
        log("用户中止")
        code = 130
    except Exception as exc:
        detail = traceback.format_exc()
        log(f"运行失败：{exc}")
        (LOGS / "last_error.txt").write_text(detail, encoding="utf-8")
        print("\n详细错误已写入 logs\\last_error.txt", flush=True)
        code = 1
    sys.exit(code)


if __name__ == "__main__":
    main()
