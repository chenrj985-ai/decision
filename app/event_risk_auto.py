from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict

import pandas as pd
import requests

from .paths import EVENTS_AUTO, DATA
from .utils import log, safe_float


NOTICE_URL = "https://np-anotice-stock.eastmoney.com/api/security/ann"
CACHE_FILE = DATA / "event_scan_cache.csv"

HARD_BAD_WORDS = (
    "立案调查", "立案告知", "行政处罚", "重大违法", "退市风险",
    "终止上市", "暂停上市", "债务逾期", "资金占用", "违规担保",
    "财务造假", "无法表示意见", "否定意见", "申请破产", "破产清算",
    "业绩预告修正", "下修业绩", "预亏", "首亏", "续亏",
    "由盈转亏", "大幅预减"
)

EARNINGS_WORDS = (
    "业绩预告", "业绩快报", "半年度业绩", "年度业绩",
    "季度报告", "半年度报告", "年度报告", "一季度报告", "三季度报告"
)

UNLOCK_WORDS = (
    "解除限售", "限售股份上市流通", "限售股上市流通",
    "首次公开发行前已发行股份", "首次公开发行限售股"
)

REDUCE_WORDS = (
    "减持计划", "拟减持", "股东减持", "集中竞价减持",
    "大宗交易减持", "减持股份预披露"
)

SOFT_RISK_WORDS = (
    "监管问询", "关注函", "问询函", "风险提示",
    "商誉减值", "资产减值", "诉讼", "仲裁",
    "高管辞职", "重大合同终止", "项目终止"
)


def _session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False
    return s


def _fetch_notices(code: str, timeout: int = 12, retries: int = 2) -> List[Dict]:
    params = {
        "sr": "-1", "page_size": "50", "page_index": "1",
        "ann_type": "A", "client_source": "web",
        "stock_list": str(code).zfill(6), "f_node": "0", "s_node": "0",
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://data.eastmoney.com/",
        "Accept": "application/json,text/plain,*/*",
    }
    last = None
    for _ in range(max(1, retries)):
        try:
            r = _session().get(NOTICE_URL, params=params, headers=headers, timeout=timeout)
            r.raise_for_status()
            payload = r.json()
            return (payload.get("data", {}) or {}).get("list", []) or []
        except Exception as exc:
            last = exc
    raise RuntimeError(str(last))


def _notice_date(item: dict):
    raw = item.get("notice_date") or item.get("display_time") or item.get("eiTime") or ""
    return pd.to_datetime(raw, errors="coerce")


def _notice_title(item: dict) -> str:
    return str(item.get("title") or item.get("notice_title") or "").strip()


def _contains(text: str, words) -> bool:
    return any(w in text for w in words)


def _load_cache() -> pd.DataFrame:
    if not CACHE_FILE.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(CACHE_FILE, dtype={"code": str})
        df["code"] = df["code"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
        return df
    except Exception:
        return pd.DataFrame()


def _save_cache(df: pd.DataFrame):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CACHE_FILE, index=False, encoding="utf-8-sig")


def refresh_auto_event_file(
    stock_df: pd.DataFrame,
    lookback_days: int = 12,
    timeout: int = 12,
) -> pd.DataFrame:
    """
    平衡防雷规则：
    - 明确重大利空：硬否决。
    - 解禁、减持、问询、业绩公告后明显下跌：严重扣分或否决。
    - 公告接口失败：优先使用72小时内缓存；无缓存时只标记“未知风险”，
      不再把全股票池直接封死，但最高只能进入B级观察。
    """
    if stock_df is None or stock_df.empty:
        return pd.DataFrame()

    now = datetime.now()
    cutoff = now - timedelta(days=int(lookback_days))
    old_cache = _load_cache()
    cache_map = {}
    if not old_cache.empty:
        for _, r in old_cache.iterrows():
            cache_map[str(r.get("code", "")).zfill(6)] = r.to_dict()

    rows, cache_rows = [], []

    for _, stock in stock_df.iterrows():
        code = str(stock.get("code", "")).zfill(6)
        name = str(stock.get("name", ""))
        pct = safe_float(stock.get("pct"))
        risk = 0.0
        hard_bad = False
        unknown = False
        notes = []
        source = "东方财富公告自动扫描"
        url = ""

        try:
            notices = _fetch_notices(code, timeout=timeout, retries=2)
            recent_earnings = False

            for item in notices:
                dt = _notice_date(item)
                if pd.isna(dt) or dt.to_pydatetime() < cutoff:
                    continue
                title = _notice_title(item)
                if not title:
                    continue

                art = str(item.get("art_code") or item.get("article_code") or "")
                if art and not url:
                    url = f"https://data.eastmoney.com/notices/detail/{code}/{art}.html"

                if _contains(title, HARD_BAD_WORDS):
                    hard_bad = True
                    risk = max(risk, 100)
                    notes.append(f"重大公告：{title}")

                if _contains(title, REDUCE_WORDS):
                    risk = max(risk, 58)
                    notes.append(f"减持风险：{title}")

                if _contains(title, UNLOCK_WORDS):
                    risk = max(risk, 52)
                    notes.append(f"解禁风险：{title}")

                if _contains(title, SOFT_RISK_WORDS):
                    risk = max(risk, 32)
                    notes.append(f"风险公告：{title}")

                if _contains(title, EARNINGS_WORDS):
                    recent_earnings = True
                    if pct <= -7:
                        hard_bad = True
                        risk = max(risk, 95)
                        notes.append(f"业绩窗口暴跌，市场确认严重预期差：{title}")
                    elif pct <= -5:
                        hard_bad = True
                        risk = max(risk, 78)
                        notes.append(f"业绩窗口大跌，疑似明显不及预期：{title}")
                    elif pct <= -3:
                        risk = max(risk, 48)
                        notes.append(f"业绩窗口显著下跌，存在预期差：{title}")
                    else:
                        risk = max(risk, 8)
                        notes.append(f"近期业绩公告：{title}")

            if pct <= -9.3:
                hard_bad = True
                risk = 100
                notes.append("当日跌停或接近跌停")
            elif pct <= -7:
                hard_bad = True
                risk = max(risk, 82)
                notes.append("当日大跌超过7%，禁止抄底")

            cache_rows.append({
                "code": code, "name": name,
                "hard_bad_news": int(hard_bad),
                "event_risk": round(min(100, risk), 1),
                "event_unknown": 0,
                "note": "；".join(dict.fromkeys(notes))[:700],
                "scan_time": now.strftime("%Y-%m-%d %H:%M:%S"),
                "source": source, "url": url,
            })

        except Exception as exc:
            cached = cache_map.get(code)
            cache_ok = False
            if cached:
                ts = pd.to_datetime(cached.get("scan_time"), errors="coerce")
                cache_ok = pd.notna(ts) and (now - ts.to_pydatetime()) <= timedelta(hours=72)

            if cache_ok:
                hard_bad = bool(int(safe_float(cached.get("hard_bad_news"))))
                risk = safe_float(cached.get("event_risk"))
                notes.append("公告接口暂时失败，采用72小时内缓存")
                old_note = str(cached.get("note", "")).strip()
                if old_note and old_note.lower() != "nan":
                    notes.append(old_note)
                source = "公告缓存"
                url = str(cached.get("url", ""))
            else:
                unknown = True
                risk = 18
                notes.append("公告接口暂时失败且无新缓存：消息面未知，降级观察但不全盘封杀")
                source = "消息面未知保护"
                log(f"公告扫描暂时失败 {code} {name}: {exc}")

        if hard_bad or risk > 0 or unknown:
            rows.append({
                "code": code, "name": name,
                "hard_bad_news": int(hard_bad),
                "event_risk": round(min(100, risk), 1),
                "event_boost": 0,
                "event_unknown": int(unknown),
                "note": "；".join(dict.fromkeys(notes))[:700],
                "expire_date": (now + timedelta(days=7)).strftime("%Y-%m-%d"),
                "source": source, "url": url,
            })

    if cache_rows:
        new_cache = pd.DataFrame(cache_rows)
        if not old_cache.empty:
            keep = old_cache[~old_cache["code"].isin(new_cache["code"])]
            new_cache = pd.concat([keep, new_cache], ignore_index=True)
        _save_cache(new_cache.tail(1000))

    columns = [
        "code", "name", "hard_bad_news", "event_risk", "event_boost",
        "event_unknown", "note", "expire_date", "source", "url"
    ]
    result = pd.DataFrame(rows, columns=columns)
    EVENTS_AUTO.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(EVENTS_AUTO, index=False, encoding="utf-8-sig")
    log(
        f"消息面扫描完成：风险/未知{len(result)}只；"
        f"硬否决{int(result['hard_bad_news'].sum()) if not result.empty else 0}只"
    )
    return result
