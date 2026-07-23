from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable, List, Dict
import re

import pandas as pd
import requests

from .paths import EVENTS_AUTO
from .utils import log, safe_float


NOTICE_URL = "https://np-anotice-stock.eastmoney.com/api/security/ann"

HARD_BAD_WORDS = (
    "立案调查", "立案告知", "行政处罚", "退市风险", "终止上市",
    "重大违法", "债务逾期", "无法偿还", "资金占用", "违规担保",
    "业绩预告修正", "下修业绩", "预亏", "首亏", "续亏",
    "大幅预减", "重大诉讼", "控制权变更失败"
)

EARNINGS_WORDS = (
    "业绩预告", "业绩快报", "半年度业绩", "年度业绩",
    "季度报告", "半年度报告"
)

UNLOCK_WORDS = (
    "解除限售", "限售股份上市流通", "限售股上市流通",
    "非公开发行限售股", "首次公开发行前已发行股份"
)

REDUCE_WORDS = (
    "减持计划", "拟减持", "股东减持", "集中竞价减持",
    "大宗交易减持"
)

OTHER_RISK_WORDS = (
    "监管问询", "关注函", "问询函", "风险提示",
    "会计差错更正", "商誉减值", "资产减值", "诉讼"
)


def _session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False
    return s


def _fetch_notices(code: str, timeout: int = 10) -> List[Dict]:
    params = {
        "sr": "-1",
        "page_size": "50",
        "page_index": "1",
        "ann_type": "A",
        "client_source": "web",
        "stock_list": str(code).zfill(6),
        "f_node": "0",
        "s_node": "0",
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://data.eastmoney.com/"
    }
    r = _session().get(NOTICE_URL, params=params, headers=headers, timeout=timeout)
    r.raise_for_status()
    data = r.json().get("data", {}) or {}
    return data.get("list", []) or []


def _notice_date(item: dict):
    raw = (
        item.get("notice_date")
        or item.get("display_time")
        or item.get("eiTime")
        or ""
    )
    return pd.to_datetime(raw, errors="coerce")


def _notice_title(item: dict) -> str:
    return str(
        item.get("title")
        or item.get("notice_title")
        or item.get("art_code")
        or ""
    ).strip()


def _contains_any(text: str, words) -> bool:
    return any(word in text for word in words)


def refresh_auto_event_file(
    stock_df: pd.DataFrame,
    lookback_days: int = 10,
    timeout: int = 10,
) -> pd.DataFrame:
    """
    自动扫描近期公告，并结合当日价格反应生成事件风险。

    重要原则：
    1. 重大明确利空直接 hard_bad_news=1；
    2. 业绩公告后当日大跌，视为“市场确认不及预期”，直接禁止新增；
    3. 解除限售/减持公告进入高风险观察；
    4. 数据源失败不阻断主程序，但写入日志。
    """
    if stock_df is None or stock_df.empty:
        return pd.DataFrame()

    cutoff = datetime.now() - timedelta(days=int(lookback_days))
    rows = []

    for _, stock in stock_df.iterrows():
        code = str(stock.get("code", "")).zfill(6)
        name = str(stock.get("name", ""))
        pct = safe_float(stock.get("pct"))
        try:
            notices = _fetch_notices(code, timeout=timeout)
        except Exception as exc:
            log(f"公告扫描失败 {code} {name}: {exc}")
            continue

        risk = 0.0
        hard_bad = False
        notes = []
        source_urls = []

        for item in notices:
            dt = _notice_date(item)
            if pd.isna(dt) or dt.to_pydatetime() < cutoff:
                continue

            title = _notice_title(item)
            if not title:
                continue

            article_code = str(
                item.get("art_code")
                or item.get("article_code")
                or ""
            )
            if article_code:
                source_urls.append(
                    "https://data.eastmoney.com/notices/detail/"
                    f"{code}/{article_code}.html"
                )

            if _contains_any(title, HARD_BAD_WORDS):
                hard_bad = True
                risk += 100
                notes.append(f"重大公告：{title}")

            if _contains_any(title, REDUCE_WORDS):
                risk += 45
                notes.append(f"股东减持风险：{title}")

            if _contains_any(title, UNLOCK_WORDS):
                risk += 40
                notes.append(f"限售股解禁风险：{title}")

            if _contains_any(title, OTHER_RISK_WORDS):
                risk += 25
                notes.append(f"风险公告：{title}")

            # 业绩公告本身不一定是利空，但公告后大跌说明市场在负面定价。
            if _contains_any(title, EARNINGS_WORDS):
                if pct <= -9.0:
                    hard_bad = True
                    risk += 80
                    notes.append(
                        f"业绩公告后跌停/接近跌停，市场确认明显低于预期：{title}"
                    )
                elif pct <= -6.0:
                    risk += 55
                    notes.append(
                        f"业绩公告后大跌，疑似低于市场预期：{title}"
                    )
                else:
                    risk += 8
                    notes.append(f"近期有业绩公告，需人工核对单季度环比：{title}")

        # 技术层面硬保护：当日跌停或接近跌停，禁止新开仓。
        if pct <= -9.3:
            hard_bad = True
            risk += 100
            notes.append("当日跌停或接近跌停，事件冷却期内禁止新增")
        elif pct <= -7.0:
            risk += 45
            notes.append("当日跌幅超过7%，禁止抄底")

        if not notes:
            continue

        expire = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        rows.append({
            "code": code,
            "name": name,
            "hard_bad_news": 1 if hard_bad else 0,
            "event_risk": min(100, round(risk, 1)),
            "event_boost": 0,
            "note": "；".join(dict.fromkeys(notes))[:500],
            "expire_date": expire,
            "source": "东方财富公告自动扫描",
            "url": source_urls[0] if source_urls else "",
        })

    df = pd.DataFrame(rows)
    if df.empty:
        df = pd.DataFrame(columns=[
            "code", "name", "hard_bad_news", "event_risk",
            "event_boost", "note", "expire_date", "source", "url"
        ])

    EVENTS_AUTO.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(EVENTS_AUTO, index=False, encoding="utf-8-sig")
    log(f"自动消息面扫描完成：发现{len(df)}只存在公告/极端下跌风险")
    return df
