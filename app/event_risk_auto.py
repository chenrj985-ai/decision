from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Dict

import pandas as pd
import requests

from .paths import EVENTS_AUTO
from .utils import log, safe_float


NOTICE_URL = "https://np-anotice-stock.eastmoney.com/api/security/ann"

# 明确重大利空：直接一票否决，不允许技术得分抵消。
HARD_BAD_WORDS = (
    "立案调查", "立案告知", "行政处罚", "重大违法", "退市风险",
    "终止上市", "暂停上市", "债务逾期", "无法偿还", "资金占用",
    "违规担保", "会计差错更正", "财务造假", "审计意见",
    "无法表示意见", "否定意见", "重大诉讼", "重大仲裁",
    "控制权变更失败", "破产重整", "申请破产", "清算",
    "业绩预告修正", "下修业绩", "预亏", "首亏", "续亏",
    "大幅预减", "由盈转亏", "同比下降超过50%"
)

# 业绩类公告：结合公告后的价格反应，识别“表面同比很好、但不及预期”。
EARNINGS_WORDS = (
    "业绩预告", "业绩快报", "半年度业绩", "年度业绩",
    "季度报告", "半年度报告", "年度报告", "一季度报告",
    "三季度报告"
)

UNLOCK_WORDS = (
    "解除限售", "限售股份上市流通", "限售股上市流通",
    "非公开发行限售股", "首次公开发行前已发行股份",
    "首次公开发行限售股"
)

REDUCE_WORDS = (
    "减持计划", "拟减持", "股东减持", "集中竞价减持",
    "大宗交易减持", "减持股份预披露"
)

OTHER_RISK_WORDS = (
    "监管问询", "关注函", "问询函", "风险提示",
    "商誉减值", "资产减值", "诉讼", "仲裁",
    "高管辞职", "董事长辞职", "总经理辞职",
    "重大合同终止", "项目终止"
)


def _session() -> requests.Session:
    session = requests.Session()
    # 避免GitHub运行环境中的异常代理影响公告接口。
    session.trust_env = False
    return session


def _fetch_notices(code: str, timeout: int = 12) -> List[Dict]:
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
        "Referer": "https://data.eastmoney.com/",
        "Accept": "application/json,text/plain,*/*",
    }
    response = _session().get(
        NOTICE_URL, params=params, headers=headers, timeout=timeout
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data", {}) or {}
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
    lookback_days: int = 12,
    timeout: int = 12,
) -> pd.DataFrame:
    """
    V7消息面安全层。

    设计原则：
    1. 保留V7原有技术选股能力，不使用V8的过严尾盘三确认。
    2. 明确重大利空一票否决，不能被量价、ETF或相对强度抵消。
    3. 业绩公告后明显下跌，按“市场确认不及预期”处理。
    4. 公告接口对某只股票失败时，该股票进入“消息面未知禁买”，
       而不是用中性值继续参加A/B级竞争。
    """
    if stock_df is None or stock_df.empty:
        return pd.DataFrame()

    cutoff = datetime.now() - timedelta(days=int(lookback_days))
    rows = []

    for _, stock in stock_df.iterrows():
        code = str(stock.get("code", "")).zfill(6)
        name = str(stock.get("name", ""))
        pct = safe_float(stock.get("pct"))
        risk = 0.0
        hard_bad = False
        notes = []
        source_urls = []

        try:
            notices = _fetch_notices(code, timeout=timeout)
        except Exception as exc:
            # 失败关闭：只禁该股，不影响其他股票继续筛选。
            log(f"公告扫描失败 {code} {name}: {exc}")
            rows.append({
                "code": code,
                "name": name,
                "hard_bad_news": 1,
                "event_risk": 70,
                "event_boost": 0,
                "note": "消息面数据获取失败，无法确认是否存在重大公告；安全模式禁止新增",
                "expire_date": datetime.now().strftime("%Y-%m-%d"),
                "source": "公告扫描失败保护",
                "url": "",
            })
            continue

        recent_earnings = False

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
                notes.append(f"重大公告一票否决：{title}")

            if _contains_any(title, REDUCE_WORDS):
                # 减持本身未必导致次日大跌，但不允许成为A/B买入候选。
                risk += 55
                notes.append(f"股东减持风险：{title}")

            if _contains_any(title, UNLOCK_WORDS):
                risk += 48
                notes.append(f"限售股解禁风险：{title}")

            if _contains_any(title, OTHER_RISK_WORDS):
                risk += 35
                notes.append(f"风险公告：{title}")

            if _contains_any(title, EARNINGS_WORDS):
                recent_earnings = True
                # 不只看同比文字，而用公告后的真实价格反应识别预期差。
                if pct <= -8.0:
                    hard_bad = True
                    risk += 100
                    notes.append(
                        f"业绩公告后暴跌，市场确认严重不及预期：{title}"
                    )
                elif pct <= -5.0:
                    hard_bad = True
                    risk += 80
                    notes.append(
                        f"业绩公告后大跌，疑似明显低于市场预期：{title}"
                    )
                elif pct <= -3.0:
                    risk += 58
                    notes.append(
                        f"业绩公告后显著下跌，存在预期差：{title}"
                    )
                else:
                    # 仅提示，不把正常业绩公告全部屏蔽。
                    risk += 10
                    notes.append(f"近期有业绩公告，需关注单季度环比：{title}")

        # 极端价格行为拥有独立保护，防止“跌停开板后技术指标漂亮”。
        if pct <= -9.3:
            hard_bad = True
            risk += 100
            notes.append("当日跌停或接近跌停，禁止新增")
        elif pct <= -7.0:
            hard_bad = True
            risk += 75
            notes.append("当日跌幅超过7%，禁止抄底")
        elif pct <= -5.0 and recent_earnings:
            hard_bad = True
            risk += 50
            notes.append("业绩窗口内大跌，进入消息面冷却期")

        if not notes:
            continue

        rows.append({
            "code": code,
            "name": name,
            "hard_bad_news": 1 if hard_bad else 0,
            "event_risk": min(100, round(risk, 1)),
            "event_boost": 0,
            "note": "；".join(dict.fromkeys(notes))[:700],
            "expire_date": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
            "source": "东方财富公告自动扫描",
            "url": source_urls[0] if source_urls else "",
        })

    columns = [
        "code", "name", "hard_bad_news", "event_risk",
        "event_boost", "note", "expire_date", "source", "url"
    ]
    df = pd.DataFrame(rows, columns=columns)
    EVENTS_AUTO.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(EVENTS_AUTO, index=False, encoding="utf-8-sig")
    log(f"自动消息面扫描完成：{len(df)}只触发公告或数据保护")
    return df
