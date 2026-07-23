from __future__ import annotations

import json
import math
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .paths import CONFIG_FILE, LOGS

ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "gbk")


DEFAULT_CONFIG = {
    "version": "6.0",
    "request_timeout": 12,
    "request_retries": 3,
    "quote_batch_size": 60,
    "quote_cache_minutes": 15,
    "quote_min_coverage": 0.75,
    "dynamic_pool_max": 120,
    "dynamic_keep_days": 10,
    "risk_keep_days": 10,
    "recommend_max": 3,
    "tail_start": "14:40",
    "max_chase_pct": 6.0,
    "market_risk_block": 68,
    "market_extreme_block": 82,
    "etf_buy_min_score": 58,
    "stock_buy_min_score": 70,
    "quick_profit_min_score": 76,
    "oversold_min_score": 78,
    "explosion_block": 60,
    "history_keep_days": 45,
    "industry_alert_drawdown_yellow": 5.0,
    "industry_alert_drawdown_orange": 9.0,
    "industry_alert_drawdown_red": 14.0,
    "use_auto_discovery": True,
    "event_lookback_days": 10,
    "auto_open_html": True,
    "international_weight": 0.15,
    "position_default_lot": 100,
    "sector_etf_map": {
        "半导体设备": "半导体ETF",
        "晶圆制造": "半导体ETF",
        "半导体材料": "半导体ETF",
        "存储芯片": "芯片ETF",
        "存储/接口芯片": "芯片ETF",
        "芯片设计": "芯片ETF",
        "国产AI芯片": "科创芯片ETF",
        "模拟芯片": "芯片ETF",
        "封测": "半导体ETF",
        "PCB": "通信ETF",
        "PCB/消费电子": "通信ETF",
        "覆铜板": "通信ETF",
        "光模块/CPO": "通信ETF",
        "光通信": "通信ETF",
        "高速铜缆": "通信ETF",
        "AI服务器": "人工智能ETF",
        "国产算力": "人工智能ETF",
        "软件": "云计算ETF",
        "软件/智能驾驶": "人工智能ETF",
        "金融科技": "大数据ETF",
        "AI应用": "人工智能ETF",
        "机器人": "机器人ETF",
        "军工": "军工ETF",
        "商业航天": "军工ETF",
        "低空经济": "军工ETF",
        "创新药": "医疗ETF",
        "CXO": "医疗ETF",
        "医疗器械": "医疗ETF",
        "医药": "医疗ETF",
        "券商": "证券ETF",
        "保险": "沪深300ETF",
        "银行": "沪深300ETF",
        "白酒消费": "酒ETF",
        "家电消费": "沪深300ETF",
        "食品消费": "沪深300ETF",
        "新能源车": "新能源车ETF",
        "光伏": "光伏ETF",
        "电力设备": "新能源车ETF",
        "有色金属": "有色金属ETF",
        "黄金": "黄金ETF",
        "煤炭": "煤炭ETF",
        "红利电力": "红利ETF"
    }
}


def log(message: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {message}"
    print(line, flush=True)
    path = LOGS / f"run_{datetime.now():%Y%m%d}.log"
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, float) and math.isnan(value):
            return default
        text = str(value).replace("%", "").replace(",", "").strip()
        if text in {"", "-", "--", "None", "nan"}:
            return default
        return float(text)
    except Exception:
        return default


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def read_csv_any(path: Path, **kwargs) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    last_error = None
    for encoding in ENCODINGS:
        try:
            return pd.read_csv(path, encoding=encoding, **kwargs)
        except UnicodeDecodeError as exc:
            last_error = exc
        except pd.errors.EmptyDataError:
            return pd.DataFrame()
    raise RuntimeError(f"无法读取文件：{path}；{last_error}")


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(
            json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        return DEFAULT_CONFIG.copy()

    try:
        custom = json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
        merged = DEFAULT_CONFIG.copy()
        merged.update(custom)
        merged["sector_etf_map"] = {
            **DEFAULT_CONFIG["sector_etf_map"],
            **custom.get("sector_etf_map", {})
        }
        return merged
    except Exception:
        backup = CONFIG_FILE.with_suffix(
            f".bad_{datetime.now():%Y%m%d_%H%M%S}.json"
        )
        shutil.copy2(CONFIG_FILE, backup)
        CONFIG_FILE.write_text(
            json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        log(f"config.json损坏，已备份为{backup.name}并恢复默认值")
        return DEFAULT_CONFIG.copy()


def symbol(code: str) -> str:
    text = str(code).strip().lower()
    if text.startswith(("sh", "sz", "bj", "hk", "us")):
        return text
    digits = "".join(ch for ch in text if ch.isdigit()).zfill(6)
    if digits.startswith(("4", "8")):
        return "bj" + digits
    return ("sh" if digits.startswith(("5", "6", "9")) else "sz") + digits


def now_is_tail(start_text: str) -> bool:
    try:
        hour, minute = [int(x) for x in start_text.split(":")]
        now = datetime.now()
        return (now.hour, now.minute) >= (hour, minute)
    except Exception:
        return False


def cleanup_old_files(folder: Path, keep_days: int) -> None:
    cutoff = datetime.now() - timedelta(days=keep_days)
    if not folder.exists():
        return
    for p in folder.iterdir():
        try:
            if p.is_file() and datetime.fromtimestamp(p.stat().st_mtime) < cutoff:
                p.unlink()
        except Exception:
            pass


def disable_environment_proxy() -> None:
    for key in (
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
        "http_proxy", "https_proxy", "all_proxy"
    ):
        os.environ.pop(key, None)
