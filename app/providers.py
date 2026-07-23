from __future__ import annotations

import json
import re
import time
from datetime import datetime
from typing import Dict, Iterable

import pandas as pd
import requests

from .models import Quote
from .paths import QUOTE_CACHE, SOURCE_HEALTH, DISCOVERY_CACHE, DISCOVERY_HEALTH
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


def _normalize_discovery_rows(rows, config: dict, source: str) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    required = ["code", "name", "amount", "pct", "turnover"]
    for col in required:
        if col not in df.columns:
            df[col] = 0.0 if col not in {"code", "name"} else ""

    df["code"] = (
        df["code"].astype(str)
        .str.replace(r"^(sh|sz|bj)", "", regex=True, case=False)
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(6)
    )
    df["name"] = df["name"].astype(str).str.strip()
    for col in ("amount", "pct", "turnover", "price"):
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    # 过滤ST、退市、北交所、新股和极端日内波动。
    bad_name = df["name"].str.contains(r"\*?ST|退", case=False, regex=True, na=False)
    new_name = df["name"].str.startswith(("N", "C"))
    bj = df["code"].str.startswith(("4", "8", "92"))
    df = df[~bad_name & ~new_name & ~bj].copy()

    min_amount = float(config.get("auto_discovery_min_amount", 1.5e8))
    max_chase = float(config.get("max_chase_pct", 6.0))
    df = df[
        (df["amount"] >= min_amount)
        & (df["pct"] <= max_chase)
        & (df["pct"] >= float(config.get("auto_discovery_min_pct", -5.5)))
        & (df["price"] >= float(config.get("auto_discovery_min_price", 3.0)))
        & (df["price"] <= float(config.get("auto_discovery_max_price", 1500.0)))
    ].copy()

    if df.empty:
        return df

    # 排名不只看涨幅，优先流动性、温和上涨和合理换手，避免追涨。
    amount_rank = df["amount"].rank(pct=True)
    pct_pref = 1 - (df["pct"] - 1.5).abs().clip(upper=8) / 8
    turn_pref = 1 - (df["turnover"] - 4.0).abs().clip(upper=20) / 20
    df["score"] = (
        45
        + amount_rank * 30
        + pct_pref * 15
        + turn_pref * 10
    ).clip(0, 100)
    df["sector"] = "自动发现"
    df["source"] = source

    return (
        df[["code", "name", "sector", "source", "score"]]
        .drop_duplicates("code")
        .sort_values("score", ascending=False)
    )


def _discover_eastmoney(config: dict) -> pd.DataFrame:
    """
    东方财富多入口重试：
    - 主域名与数字子域名；
    - HTTPS与HTTP；
    - 同时尝试忽略系统代理、使用系统代理两种连接模式。
    """
    hosts = [
        "https://push2.eastmoney.com/api/qt/clist/get",
        "https://82.push2.eastmoney.com/api/qt/clist/get",
        "https://20.push2.eastmoney.com/api/qt/clist/get",
        "http://push2.eastmoney.com/api/qt/clist/get",
    ]
    errors = []

    for url in hosts:
        for trust_env in (False, True):
            rows = []
            session = requests.Session()
            session.trust_env = trust_env
            try:
                for page in range(1, int(config.get("auto_discovery_pages", 3)) + 1):
                    params = {
                        "pn": page,
                        "pz": int(config.get("auto_discovery_page_size", 200)),
                        "po": 1,
                        "np": 1,
                        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                        "fltt": 2,
                        "invt": 2,
                        "fid": "f6",
                        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
                        "fields": "f12,f14,f2,f3,f6,f8,f15,f16,f17,f18",
                        "_": int(time.time() * 1000),
                    }
                    response = session.get(
                        url,
                        params=params,
                        timeout=int(config.get("request_timeout", 12)),
                        headers={
                            "User-Agent": (
                                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 Chrome/124 Safari/537.36"
                            ),
                            "Referer": "https://quote.eastmoney.com/",
                            "Accept": "application/json,text/plain,*/*",
                            "Connection": "close",
                        }
                    )
                    response.raise_for_status()
                    payload = response.json()
                    diff = (payload.get("data") or {}).get("diff") or []
                    if not diff:
                        break
                    for item in diff:
                        rows.append({
                            "code": item.get("f12", ""),
                            "name": item.get("f14", ""),
                            "price": safe_float(item.get("f2")),
                            "pct": safe_float(item.get("f3")),
                            "amount": safe_float(item.get("f6")),
                            "turnover": safe_float(item.get("f8")),
                        })
                df = _normalize_discovery_rows(rows, config, "东方财富成交额排行")
                if len(df) >= int(config.get("auto_discovery_min_rows", 15)):
                    return df
                errors.append(f"{url} rows={len(df)}")
            except Exception as exc:
                errors.append(f"{url} proxy={trust_env}: {type(exc).__name__}")
                time.sleep(0.5)
    raise RuntimeError("；".join(errors[-8:]))


def _discover_sina(config: dict) -> pd.DataFrame:
    url = (
        "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        "Market_Center.getHQNodeData"
    )
    rows = []
    errors = []

    for trust_env in (False, True):
        session = requests.Session()
        session.trust_env = trust_env
        try:
            for page in range(1, int(config.get("auto_discovery_pages", 3)) + 1):
                params = {
                    "page": page,
                    "num": int(config.get("auto_discovery_page_size", 200)),
                    "sort": "amount",
                    "asc": 0,
                    "node": "hs_a",
                    "symbol": "",
                    "_s_r_a": "page",
                }
                response = session.get(
                    url,
                    params=params,
                    timeout=int(config.get("request_timeout", 12)),
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Referer": "https://finance.sina.com.cn/",
                        "Connection": "close",
                    }
                )
                response.raise_for_status()
                data = response.json()
                if not data:
                    break
                for item in data:
                    price = safe_float(item.get("trade") or item.get("price"))
                    prev = safe_float(item.get("settlement") or item.get("prev_close"))
                    pct = safe_float(item.get("changepercent"))
                    if pct == 0 and price > 0 and prev > 0:
                        pct = (price / prev - 1) * 100
                    amount = safe_float(item.get("amount"))
                    if amount <= 0:
                        amount = safe_float(item.get("volume")) * price
                    rows.append({
                        "code": item.get("code") or item.get("symbol", ""),
                        "name": item.get("name", ""),
                        "price": price,
                        "pct": pct,
                        "amount": amount,
                        "turnover": safe_float(item.get("turnoverratio")),
                    })
            df = _normalize_discovery_rows(rows, config, "新浪财经成交额排行")
            if len(df) >= int(config.get("auto_discovery_min_rows", 15)):
                return df
            errors.append(f"rows={len(df)}")
        except Exception as exc:
            errors.append(f"proxy={trust_env}: {type(exc).__name__}")
    raise RuntimeError("；".join(errors[-4:]))


def _discover_tencent_rank(config: dict) -> pd.DataFrame:
    """
    腾讯排行接口作为第三实时源。接口字段可能精简，因此只要求代码、
    名称、价格、涨跌幅和成交额可解析。
    """
    urls = [
        "https://stock.gtimg.cn/data/index.php",
        "http://stock.gtimg.cn/data/index.php",
    ]
    errors = []

    for url in urls:
        for trust_env in (False, True):
            session = requests.Session()
            session.trust_env = trust_env
            try:
                rows = []
                for page in range(1, 5):
                    params = {
                        "appn": "rank",
                        "t": "rankash/chr",
                        "p": page,
                        "o": 0,
                        "l": 100,
                        "v": "list_data",
                    }
                    response = session.get(
                        url,
                        params=params,
                        timeout=int(config.get("request_timeout", 12)),
                        headers={
                            "User-Agent": "Mozilla/5.0",
                            "Referer": "https://stockapp.finance.qq.com/",
                            "Connection": "close",
                        }
                    )
                    response.raise_for_status()
                    response.encoding = "gbk"
                    body = response.text

                    # 常见返回中每条记录以 ~ 分隔字段，以逗号或引号分隔股票。
                    records = re.findall(r'"([^"]*~[^"]*)"', body)
                    if not records:
                        records = [x for x in body.split(",") if "~" in x]

                    for rec in records:
                        parts = rec.strip().strip('"').split("~")
                        if len(parts) < 6:
                            continue
                        # 尝试从字段中识别6位代码。
                        code = next(
                            (x for x in parts if re.fullmatch(r"\d{6}", x.strip())),
                            ""
                        )
                        if not code:
                            continue
                        name = parts[1].strip() if len(parts) > 1 else ""
                        nums = [safe_float(x) for x in parts]
                        price = nums[3] if len(nums) > 3 else 0
                        pct = nums[5] if len(nums) > 5 else 0
                        amount = max(nums) if nums else 0
                        rows.append({
                            "code": code,
                            "name": name,
                            "price": price,
                            "pct": pct,
                            "amount": amount,
                            "turnover": 0,
                        })
                df = _normalize_discovery_rows(rows, config, "腾讯股票排行")
                if len(df) >= int(config.get("auto_discovery_min_rows", 10)):
                    return df
                errors.append(f"{url} rows={len(df)}")
            except Exception as exc:
                errors.append(f"{url} proxy={trust_env}: {type(exc).__name__}")
    raise RuntimeError("；".join(errors[-6:]))


def _save_discovery_cache(df: pd.DataFrame, source: str) -> None:
    if df is None or df.empty:
        return
    cached = df.copy()
    cached["cache_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cached["live_source"] = source
    DISCOVERY_CACHE.parent.mkdir(parents=True, exist_ok=True)
    cached.to_csv(DISCOVERY_CACHE, index=False, encoding="utf-8-sig")


def _load_discovery_cache(config: dict) -> pd.DataFrame:
    if not DISCOVERY_CACHE.exists():
        return pd.DataFrame()
    try:
        age_hours = (
            datetime.now() - datetime.fromtimestamp(DISCOVERY_CACHE.stat().st_mtime)
        ).total_seconds() / 3600
        if age_hours > float(config.get("auto_discovery_cache_hours", 72)):
            return pd.DataFrame()
        df = read_csv_any(DISCOVERY_CACHE, dtype={"code": str})
        if df.empty:
            return df
        df["code"] = df["code"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
        df["source"] = "自动发现缓存"
        # 缓存略微降分，但仍然属于自动池，不退回核心池。
        df["score"] = pd.to_numeric(df.get("score"), errors="coerce").fillna(50) - 3
        return df[["code", "name", "sector", "source", "score"]]
    except Exception:
        return pd.DataFrame()


def auto_discover(config: dict) -> pd.DataFrame:
    """
    多源自动发现：
    东方财富 → 新浪财经 → 腾讯排行 → 72小时缓存。

    即使东方财富单源不可用，也不会立即退回“仅核心池”。
    """
    if not config.get("use_auto_discovery", True):
        return pd.DataFrame()

    attempts = []
    source_used = ""
    result = pd.DataFrame()

    sources = [
        ("东方财富", _discover_eastmoney),
        ("新浪财经", _discover_sina),
        ("腾讯排行", _discover_tencent_rank),
    ]

    for source_name, func in sources:
        try:
            candidate = func(config)
            if candidate is not None and not candidate.empty:
                result = candidate.head(int(config.get("dynamic_pool_max", 80))).copy()
                source_used = source_name
                _save_discovery_cache(result, source_name)
                log(f"自动发现成功：{source_name}，发现{len(result)}只候选")
                break
        except Exception as exc:
            attempts.append(f"{source_name}:{str(exc)[:180]}")
            log(f"{source_name}自动发现失败，继续切换备用源：{type(exc).__name__}")

    cache_used = False
    if result.empty:
        result = _load_discovery_cache(config)
        if not result.empty:
            cache_used = True
            source_used = "72小时自动发现缓存"
            log(f"实时自动发现源均不可用，使用缓存候选{len(result)}只")
        else:
            source_used = "无可用实时源且无缓存"
            log("自动发现所有实时源均失败，且暂无缓存；本次才退回核心池和持仓")

    health = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": source_used,
        "rows": int(len(result)),
        "cache_used": cache_used,
        "attempts": attempts[-12:],
    }
    DISCOVERY_HEALTH.write_text(
        json.dumps(health, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    return result

