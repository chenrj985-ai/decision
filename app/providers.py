from __future__ import annotations

import json
import re
import time
from datetime import datetime
from typing import Dict, Iterable

import pandas as pd
import requests

from .models import Quote
from .paths import QUOTE_CACHE, SOURCE_HEALTH
from .utils import log, read_csv_any, safe_float, symbol


def _session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    return session


def save_quote_cache(quotes: Dict[str, Quote]) -> None:
    if not quotes:
        return
    pd.DataFrame([q.to_dict() for q in quotes.values()]).to_csv(
        QUOTE_CACHE, index=False, encoding="utf-8-sig"
    )


def load_quote_cache(max_minutes: int) -> Dict[str, Quote]:
    if not QUOTE_CACHE.exists():
        return {}
    age_minutes = (
        datetime.now() - datetime.fromtimestamp(QUOTE_CACHE.stat().st_mtime)
    ).total_seconds() / 60
    if age_minutes > max_minutes:
        return {}

    try:
        df = read_csv_any(QUOTE_CACHE, dtype=str)
        out: Dict[str, Quote] = {}
        for _, row in df.iterrows():
            q = Quote(
                symbol=str(row.get("symbol", "")).lower(),
                code=str(row.get("code", "")),
                name=str(row.get("name", "")),
                price=safe_float(row.get("price")),
                pre_close=safe_float(row.get("pre_close")),
                open=safe_float(row.get("open")),
                high=safe_float(row.get("high")),
                low=safe_float(row.get("low")),
                pct=safe_float(row.get("pct")),
                change=safe_float(row.get("change")),
                amount=safe_float(row.get("amount")),
                turnover=safe_float(row.get("turnover")),
                volume_ratio=safe_float(row.get("volume_ratio")),
                quote_time=str(row.get("quote_time", ""))
            )
            if q.symbol and q.price > 0:
                out[q.symbol] = q
        return out
    except Exception:
        return {}


def fetch_tencent(
    symbols: Iterable[str],
    config: dict
) -> Dict[str, Quote]:
    requested = list(dict.fromkeys(
        symbol(item) for item in symbols if str(item).strip()
    ))
    result: Dict[str, Quote] = {}
    errors = []
    timeout = int(config["request_timeout"])
    retries = int(config["request_retries"])
    batch_size = int(config.get("quote_batch_size", 60))
    headers = {
        "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Referer": "https://stockapp.finance.qq.com/",
        "Accept": "*/*",
        "Connection": "close"
    }

    session = _session()
    for start in range(0, len(requested), batch_size):
        batch = requested[start:start + batch_size]
        url = "https://qt.gtimg.cn/q=" + ",".join(batch)
        text = None
        last_error = None

        for attempt in range(retries):
            try:
                response = session.get(url, headers=headers, timeout=timeout)
                response.raise_for_status()
                response.encoding = "gbk"
                text = response.text
                if 'v_' not in text:
                    raise RuntimeError("腾讯行情返回格式异常")
                break
            except Exception as exc:
                last_error = exc
                time.sleep(1.0 + attempt * 1.2)

        if text is None:
            errors.append(f"{batch[0]}..{batch[-1]}：{last_error}")
            continue

        for line in text.splitlines():
            match = re.search(r'v_([^=]+)="(.*)";', line)
            if not match:
                continue
            raw_symbol = match.group(1).lower()
            parts = match.group(2).split("~")
            if len(parts) < 40:
                continue

            quote = Quote(
                symbol=raw_symbol,
                code=parts[2].strip() if len(parts) > 2 else raw_symbol[-6:],
                name=parts[1].strip(),
                price=safe_float(parts[3]),
                pre_close=safe_float(parts[4]),
                open=safe_float(parts[5]),
                change=safe_float(parts[31]),
                pct=safe_float(parts[32]),
                high=safe_float(parts[33]),
                low=safe_float(parts[34]),
                amount=safe_float(parts[37]),
                turnover=safe_float(parts[38]),
                volume_ratio=safe_float(parts[49]) if len(parts) > 49 else 0.0,
                quote_time=parts[30] if len(parts) > 30 else ""
            )
            if quote.price > 0:
                result[raw_symbol] = quote

    cache_used = False
    if result:
        save_quote_cache(result)
    else:
        cached = load_quote_cache(int(config.get("quote_cache_minutes", 15)))
        if cached:
            result = cached
            cache_used = True
            log(f"腾讯实时行情失败，启用{len(cached)}条短时缓存")

    health = {
        "source": "腾讯财经",
        "requested": len(requested),
        "received": len(result),
        "coverage": round(len(result) / max(1, len(requested)), 4),
        "errors": errors[:10],
        "cache_used": cache_used,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    SOURCE_HEALTH.write_text(
        json.dumps(health, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    log(
        f"腾讯行情覆盖率：{health['received']}/{health['requested']} "
        f"= {health['coverage']:.1%}"
    )
    return result


def auto_discover(config: dict) -> pd.DataFrame:
    """
    东方财富仅用于发现高成交额股票。
    失败时返回空表，不影响腾讯核心行情。
    """
    if not config.get("use_auto_discovery", True):
        return pd.DataFrame()

    url = "https://push2.eastmoney.com/api/qt/clist/get"
    rows = []
    session = _session()
    try:
        for page in range(1, 4):
            params = {
                "pn": page,
                "pz": 200,
                "po": 1,
                "np": 1,
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                "fltt": 2,
                "invt": 2,
                "fid": "f6",
                "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
                "fields": "f12,f14,f2,f3,f6,f8,f15,f16,f17,f18"
            }
            response = session.get(
                url,
                params=params,
                timeout=int(config["request_timeout"]),
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": "https://quote.eastmoney.com/"
                }
            )
            response.raise_for_status()
            diff = response.json().get("data", {}).get("diff", []) or []
            if not diff:
                break

            for item in diff:
                code = str(item.get("f12", "")).zfill(6)
                name = str(item.get("f14", ""))
                amount = safe_float(item.get("f6"))
                pct = safe_float(item.get("f3"))
                turnover = safe_float(item.get("f8"))

                if not code or "ST" in name.upper() or "退" in name:
                    continue
                if amount < 2e8:
                    continue
                if pct > float(config["max_chase_pct"]) or pct < -7:
                    continue

                liquidity = min(28, max(0, (len(str(int(amount))) - 7) * 5))
                score = 45 + liquidity + min(15, pct * 2) + min(12, turnover)
                rows.append({
                    "code": code,
                    "name": name,
                    "sector": "自动发现",
                    "source": "东方财富成交额",
                    "score": round(max(0, min(100, score)), 2)
                })

        if not rows:
            return pd.DataFrame()

        return (
            pd.DataFrame(rows)
            .drop_duplicates("code")
            .sort_values("score", ascending=False)
            .head(int(config["dynamic_pool_max"]))
        )
    except Exception as exc:
        log(f"东方财富自动发现不可用，继续使用核心池和持仓：{exc}")
        return pd.DataFrame()
