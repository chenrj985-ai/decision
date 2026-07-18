# -*- coding: utf-8 -*-
"""V5.1.1 自动风险更新。

改进：
1. GDELT 由 6 次连续请求改为 1 次合并请求，显著降低 429 概率；
2. 对 429、空响应、非 JSON 响应做明确处理，不再出现二次 JSON 解析报错；
3. 增加 6 小时新闻缓存；接口失败时沿用有效缓存，不覆盖为空；
4. GDELT 不可用时尝试 Google News RSS 单次合并查询；
5. 任何新闻源失败均不阻断行情、公告和主程序。
"""
from __future__ import annotations

import json
import re
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import quote_plus

import pandas as pd
import requests

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
LOGS = BASE / "logs"
CACHE = DATA / "cache"
DATA.mkdir(exist_ok=True)
LOGS.mkdir(exist_ok=True)
CACHE.mkdir(exist_ok=True)

AUTO_GLOBAL = DATA / "global_risk_auto.csv"
AUTO_EVENT = DATA / "event_risk_auto.csv"
POSITIONS = DATA / "my_positions.csv"
SEED = BASE / "stock_pool_seed.csv"
NEWS_CACHE = CACHE / "news_cache.json"

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,text/html,application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
}
SESSION = requests.Session()
SESSION.headers.update(UA)


class RateLimitedError(RuntimeError):
    pass


def log(s: str) -> None:
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {s}"
    print(line, flush=True)
    with (LOGS / "risk_update.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def request_response(url: str, params=None, timeout: int = 15, retries: int = 2) -> requests.Response:
    """通用请求。429 不做快速重试，避免进一步触发限流。"""
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = SESSION.get(url, params=params, timeout=timeout)
            if r.status_code == 429:
                retry_after = r.headers.get("Retry-After", "稍后")
                raise RateLimitedError(f"接口限流(429)，建议 {retry_after} 秒后再试")
            if r.status_code in (403, 451):
                raise RuntimeError(f"接口拒绝访问({r.status_code})")
            r.raise_for_status()
            return r
        except RateLimitedError:
            raise
        except Exception as ex:
            last_error = ex
            if attempt < retries:
                time.sleep(2 + attempt * 2)
    raise last_error or RuntimeError("网络请求失败")


def get_json(url: str, params=None, timeout: int = 15, retries: int = 2) -> dict:
    r = request_response(url, params=params, timeout=timeout, retries=retries)
    content_type = (r.headers.get("Content-Type") or "").lower()
    text = (r.text or "").strip()
    if not text:
        raise RuntimeError("接口返回空内容")
    if "json" not in content_type and not text.startswith(("{", "[")):
        preview = re.sub(r"\s+", " ", text[:100])
        raise RuntimeError(f"接口未返回JSON：{preview}")
    try:
        return r.json()
    except Exception as ex:
        raise RuntimeError(f"JSON解析失败：{ex}") from ex


def yahoo_changes(ticker: str) -> Tuple[float, float, float]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(ticker, safe='')}"
    j = get_json(url, {"range": "10d", "interval": "1d", "includePrePost": "false"})
    result = (j.get("chart") or {}).get("result") or []
    if not result:
        raise RuntimeError("Yahoo无有效行情结果")
    closes = result[0]["indicators"]["quote"][0]["close"]
    q = [float(x) for x in closes if x is not None]
    if len(q) < 2:
        raise RuntimeError("历史数据不足")
    d1 = (q[-1] / q[-2] - 1) * 100
    d5 = (q[-1] / q[max(0, len(q) - 6)] - 1) * 100
    return q[-1], d1, d5


def market_rows() -> List[dict]:
    specs = {
        "^VIX": ("VIX恐慌指数", "全市场", 1),
        "^SOX": ("费城半导体指数", "半导体/CPO/PCB/存储", -1),
        "^IXIC": ("纳斯达克指数", "科技成长", -1),
        "^TNX": ("美国10年期收益率", "高估值成长", 1),
        "DX-Y.NYB": ("美元指数", "外资/成长", 1),
        "CNY=X": ("美元兑人民币", "外资/成长", 1),
        "CL=F": ("国际原油", "航空/化工下游", 1),
        "GC=F": ("国际黄金", "避险情绪", 1),
        "NVDA": ("英伟达", "CPO/PCB/AI服务器", -1),
        "MU": ("美光科技", "存储芯片", -1),
        "TSM": ("台积电ADR", "半导体设备/晶圆制造", -1),
    }
    rows: List[dict] = []
    today = f"{datetime.now():%Y-%m-%d}"
    for ticker, (name, sector, polarity) in specs.items():
        try:
            price, d1, d5 = yahoo_changes(ticker)
            impact = 0.0
            direction = "risk"
            note = f"最新{price:.2f}，1日{d1:+.2f}%，5日{d5:+.2f}%"
            if ticker == "^VIX":
                impact = max(0, (price - 18) * 0.9) + max(0, d1) * 0.35
            elif ticker == "^TNX":
                impact = max(0, d5) * 1.5 + max(0, d1) * 1.2
            elif ticker in {"DX-Y.NYB", "CNY=X"}:
                impact = max(0, d5) * 2.0 + max(0, d1) * 1.5
            elif ticker == "CL=F":
                impact = max(0, d5 - 3) * 0.8 + max(0, d1 - 2) * 0.8
            elif ticker == "GC=F":
                impact = max(0, d5 - 3) * 0.5
            else:
                impact = max(0, -d1) * 1.3 + max(0, -d5) * 0.8
            if impact < 1.5 and ((polarity < 0 and d5 > 2) or (ticker == "^VIX" and d5 < -5)):
                direction = "positive"
                impact = min(8, abs(d5) * 0.5)
            if impact >= 1.5:
                rows.append({
                    "date": today, "item": name, "direction": direction,
                    "impact": round(min(25, impact), 1), "sector": sector,
                    "note": note, "source": "Yahoo Finance chart", "url": ""
                })
            log(f"[OK] 全球行情 {name}: {note}")
        except Exception as e:
            log(f"[WARN] 全球行情 {name} 获取失败: {e}")
    return rows


NEWS_RULES = [
    {
        "label": "芯片出口限制/制裁", "sector": "半导体设备/国产算力/CPO", "base": 15,
        "terms": ["chip export", "semiconductor sanction", "ai chip ban", "export restriction", "芯片出口", "半导体制裁"]
    },
    {
        "label": "AI资本开支变化", "sector": "CPO/PCB/AI服务器", "base": 12,
        "terms": ["nvidia capex", "ai spending", "data center spending", "capital expenditure", "资本开支", "数据中心支出"]
    },
    {
        "label": "存储价格与供需", "sector": "存储芯片/封测", "base": 12,
        "terms": ["memory chip", "dram", "nand", "oversupply", "存储价格", "存储芯片"]
    },
    {
        "label": "中东冲突与能源运输", "sector": "全市场/原油/军工/黄金", "base": 14,
        "terms": ["middle east conflict", "oil shipping", "shipping disruption", "中东冲突", "航运中断", "原油运输"]
    },
    {
        "label": "关税与科技贸易摩擦", "sector": "科技成长/出口链", "base": 12,
        "terms": ["us tariff china", "technology trade", "trade restriction", "关税", "科技贸易摩擦"]
    },
    {
        "label": "美联储与利率风险", "sector": "高估值成长", "base": 10,
        "terms": ["federal reserve", "rate hike", "bond yields", "inflation", "美联储", "加息", "美债收益率"]
    },
]
NEG = ["ban", "restrict", "sanction", "war", "attack", "conflict", "cut", "decline", "plunge", "tariff", "risk", "shortage", "oversupply", "investigation", "制裁", "限制", "冲突", "下调", "下降", "风险"]
POS = ["ease", "approve", "deal", "increase", "growth", "stimulus", "support", "recovery", "放宽", "批准", "增长", "刺激", "支持", "复苏"]


def load_news_cache(max_age_hours: int = 6) -> List[dict]:
    try:
        obj = json.loads(NEWS_CACHE.read_text(encoding="utf-8"))
        ts = datetime.fromisoformat(obj["updated_at"])
        if datetime.now() - ts <= timedelta(hours=max_age_hours):
            rows = obj.get("rows") or []
            if rows:
                log(f"[OK] 使用新闻缓存：{len(rows)}条，更新时间 {ts:%Y-%m-%d %H:%M}")
                return rows
    except Exception:
        pass
    return []


def save_news_cache(rows: List[dict]) -> None:
    if not rows:
        return
    NEWS_CACHE.write_text(
        json.dumps({"updated_at": datetime.now().isoformat(timespec="seconds"), "rows": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def article_to_rule(title: str) -> List[dict]:
    low = title.lower()
    matched = []
    for rule in NEWS_RULES:
        if any(term.lower() in low for term in rule["terms"]):
            matched.append(rule)
    return matched


def build_news_rows(articles: List[dict], source_name: str) -> List[dict]:
    today = f"{datetime.now():%Y-%m-%d}"
    buckets: Dict[str, List[tuple]] = {r["label"]: [] for r in NEWS_RULES}
    seen = set()
    for a in articles:
        title = re.sub(r"\s+", " ", str(a.get("title", "")).strip())
        url = str(a.get("url", ""))
        domain = str(a.get("domain", "")) or re.sub(r"^www\.", "", str(a.get("source", "")))
        key = re.sub(r"\W+", "", title.lower())[:100]
        if not title or key in seen:
            continue
        seen.add(key)
        for rule in article_to_rule(title):
            buckets[rule["label"]].append((title, url, domain))

    rows: List[dict] = []
    for rule in NEWS_RULES:
        picked = buckets[rule["label"]]
        if not picked:
            continue
        titles = " ".join(x[0].lower() for x in picked[:10])
        neg = sum(titles.count(x) for x in NEG)
        pos = sum(titles.count(x) for x in POS)
        direction = "risk" if neg >= pos else "positive"
        domains = {x[2] for x in picked if x[2]}
        impact = min(22, rule["base"] + min(6, max(0, len(domains) - 1)))
        summary = "；".join(x[0] for x in picked[:3])[:360]
        rows.append({
            "date": today, "item": rule["label"], "direction": direction,
            "impact": impact, "sector": rule["sector"],
            "note": f"{len(picked)}条新闻/{max(1, len(domains))}个来源：{summary}",
            "source": source_name, "url": picked[0][1],
        })
    return rows


def gdelt_rows_single_request() -> List[dict]:
    # 合并成一个请求，避免原先六连请求触发 429。
    query = (
        '("chip export" OR "semiconductor sanctions" OR "AI chip ban" OR '
        '"AI spending" OR "data center spending" OR "memory chip" OR DRAM OR NAND OR '
        '"Middle East conflict" OR "oil shipping" OR "US tariff China" OR '
        '"Federal Reserve" OR "bond yields")'
    )
    j = get_json(
        "https://api.gdeltproject.org/api/v2/doc/doc",
        {
            "query": query,
            "mode": "ArtList",
            "maxrecords": 100,
            "format": "json",
            "sort": "HybridRel",
            "timespan": "2d",
        },
        timeout=25,
        retries=0,
    )
    arts = j.get("articles") or []
    rows = build_news_rows(arts, "GDELT")
    if not rows:
        raise RuntimeError("GDELT返回新闻，但未匹配到风险主题")
    log(f"[OK] GDELT单次合并查询成功：原始{len(arts)}条，分类后{len(rows)}类")
    return rows


def google_news_rss_rows() -> List[dict]:
    # 备用源也只做一次合并请求。
    query = (
        'chip export semiconductor sanctions AI spending data center memory DRAM NAND '
        'Middle East conflict oil shipping US China tariff Federal Reserve bond yields'
    )
    url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
    r = request_response(url, timeout=25, retries=1)
    root = ET.fromstring(r.content)
    articles = []
    for item in root.findall(".//item")[:100]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        source_node = item.find("source")
        source = (source_node.text or "").strip() if source_node is not None else ""
        articles.append({"title": title, "url": link, "domain": source})
    rows = build_news_rows(articles, "Google News RSS")
    if not rows:
        raise RuntimeError("备用RSS未匹配到风险主题")
    log(f"[OK] 备用RSS成功：原始{len(articles)}条，分类后{len(rows)}类")
    return rows


def news_rows() -> List[dict]:
    cached = load_news_cache(max_age_hours=6)
    if cached:
        return cached

    try:
        rows = gdelt_rows_single_request()
        save_news_cache(rows)
        return rows
    except RateLimitedError as e:
        log(f"[WARN] GDELT {e}；不再连续重试，转用备用RSS")
    except Exception as e:
        log(f"[WARN] GDELT新闻获取失败: {e}；转用备用RSS")

    try:
        rows = google_news_rss_rows()
        save_news_cache(rows)
        return rows
    except Exception as e:
        log(f"[WARN] 备用RSS获取失败: {e}")

    # 即使缓存超过6小时，只要不超过48小时，也优先沿用，避免把风险新闻清空。
    stale = load_news_cache(max_age_hours=48)
    if stale:
        log("[WARN] 新闻接口均不可用，沿用48小时内旧缓存")
        return stale
    log("[WARN] 新闻接口均不可用且无缓存，本次仅使用全球行情和ETF风险")
    return []


BAD_HARD = ["立案调查", "重大违法", "退市风险", "终止上市", "审计报告无法表示意见", "债务逾期", "破产重整"]
BAD = ["减持", "业绩预亏", "业绩预减", "亏损", "风险提示", "诉讼", "仲裁", "解禁", "质押", "问询函", "监管措施", "处罚"]
GOOD = ["业绩预增", "扭亏为盈", "回购", "增持", "中标", "订单", "项目获批", "产品认证"]


def load_codes() -> List[dict]:
    frames = []
    for p in [POSITIONS, SEED]:
        try:
            frames.append(pd.read_csv(p, encoding="utf-8-sig", dtype=str))
        except Exception:
            pass
    if not frames:
        return []
    df = pd.concat(frames, ignore_index=True)
    df["code"] = df["code"].astype(str).str.extract(r"(\d+)")[0].str.zfill(6)
    return df.dropna(subset=["code"]).drop_duplicates("code")[["code", "name"]].head(160).to_dict("records")


def announcement_rows() -> List[dict]:
    codes = load_codes()
    names = {x["code"]: x.get("name", "") for x in codes}
    out: List[dict] = []
    today = datetime.now().date()
    for i in range(0, len(codes), 25):
        chunk = ",".join(x["code"] for x in codes[i:i + 25])
        try:
            j = get_json(
                "https://np-anotice-stock.eastmoney.com/api/security/ann",
                {"sr": "-1", "page_size": "100", "page_index": "1", "ann_type": "A", "client_source": "web", "stock_list": chunk},
                timeout=18,
            )
            items = ((j.get("data") or {}).get("list") or [])
            for a in items:
                title = str(a.get("title", "")).strip()
                dt = str(a.get("notice_date", ""))[:10]
                try:
                    d = pd.to_datetime(dt).date()
                except Exception:
                    continue
                if (today - d).days > 4:
                    continue
                for st in a.get("codes") or []:
                    code = str(st.get("stock_code", "")).zfill(6)
                    if code not in names:
                        continue
                    hard = any(k in title for k in BAD_HARD)
                    risk = sum(k in title for k in BAD) * 4 + (22 if hard else 0)
                    boost = sum(k in title for k in GOOD) * 4
                    if risk == 0 and boost == 0:
                        continue
                    out.append({
                        "code": code, "name": names[code], "hard_bad_news": 1 if hard else 0,
                        "event_risk": min(35, risk), "event_boost": min(16, boost),
                        "note": f"{dt}公告：{title}",
                        "expire_date": str(today + timedelta(days=12 if risk else 7)),
                        "source": "东方财富公告", "url": "",
                    })
            log(f"[OK] 公告批次 {i // 25 + 1}: {len(items)}条")
        except Exception as e:
            log(f"[WARN] 公告批次 {i // 25 + 1} 获取失败: {e}")
        # 公告接口也留出小间隔，降低被限流概率。
        if i + 25 < len(codes):
            time.sleep(1.2)

    if not out:
        return []
    df = pd.DataFrame(out)
    agg = []
    for code, g in df.groupby("code"):
        agg.append({
            "code": code, "name": g.iloc[0]["name"],
            "hard_bad_news": int(g["hard_bad_news"].astype(int).max()),
            "event_risk": min(35, g["event_risk"].astype(float).sum()),
            "event_boost": min(16, g["event_boost"].astype(float).sum()),
            "note": "；".join(g["note"].astype(str).tolist())[:500],
            "expire_date": g["expire_date"].max(), "source": "东方财富公告", "url": "",
        })
    return agg


def write(rows: List[dict], path: Path, cols: List[str]) -> None:
    pd.DataFrame(rows, columns=cols).to_csv(path, index=False, encoding="utf-8-sig")


def main() -> int:
    log("V5.1.1自动风险更新开始（限流缓存修复版）")
    market = market_rows()
    news = news_rows()
    events = announcement_rows()
    write(market + news, AUTO_GLOBAL, ["date", "item", "direction", "impact", "sector", "note", "source", "url"])
    write(events, AUTO_EVENT, ["code", "name", "hard_bad_news", "event_risk", "event_boost", "note", "expire_date", "source", "url"])
    log(f"自动风险更新完成：行情{len(market)}条，新闻{len(news)}条，个股公告{len(events)}只")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        (LOGS / "risk_update_last_error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        log("[ERROR] 自动风险模块异常，主程序仍可继续")
        sys.exit(2)
