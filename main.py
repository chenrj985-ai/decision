# -*- coding: utf-8 -*-
"""
StockDecisionSystem V6 Cloud
Market regime + ETF rotation + dynamic pool + risk engine + recommendation tracking.
Designed for Windows one-click execution with graceful fallback.
"""
from __future__ import annotations

import csv
import json
import math
import os
import re
import shutil
import sys
import time
import traceback
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean, pstdev
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd
import requests

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
OUT = BASE / "output"
LOGS = BASE / "logs"
HISTORY = OUT / "history"
TRACK = DATA / "recommendation_history.csv"
DYNAMIC_POOL = DATA / "dynamic_pool.csv"
RISK_POOL = DATA / "risk_pool.csv"
POSITIONS = DATA / "my_positions.csv"
EVENTS = DATA / "event_risk.csv"
GLOBAL_MANUAL = DATA / "global_risk_manual.csv"
GLOBAL_AUTO = DATA / "global_risk_auto.csv"
EVENTS_AUTO = DATA / "event_risk_auto.csv"
CONFIG_FILE = BASE / "config.json"
SEED_POOL = BASE / "stock_pool_seed.csv"
MARKET_POOL = BASE / "market_pool.csv"

for d in (DATA, OUT, LOGS, HISTORY):
    d.mkdir(parents=True, exist_ok=True)

ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "gbk")

DEFAULT_CONFIG = {
    "version": "6.0",
    "request_timeout": 12,
    "request_retries": 3,
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
    "history_keep_days": 45,
    "industry_alert_drawdown_yellow": 5.0,
    "industry_alert_drawdown_orange": 9.0,
    "industry_alert_drawdown_red": 14.0,
    "use_auto_discovery": True,
    "auto_open_html": False,
    "international_weight": 0.25,
    "position_default_lot": 100,
    "sector_etf_map": {
        "半导体设备": "半导体ETF", "晶圆制造": "半导体ETF", "半导体材料": "半导体ETF",
        "存储芯片": "芯片ETF", "存储/接口芯片": "芯片ETF", "芯片设计": "芯片ETF",
        "国产AI芯片": "科创芯片ETF", "模拟芯片": "芯片ETF", "封测": "半导体ETF",
        "PCB": "通信ETF", "PCB/消费电子": "通信ETF", "覆铜板": "通信ETF",
        "光模块/CPO": "通信ETF", "光通信": "通信ETF", "高速铜缆": "通信ETF",
        "AI服务器": "人工智能ETF", "国产算力": "人工智能ETF", "软件": "云计算ETF",
        "软件/智能驾驶": "人工智能ETF", "金融科技": "大数据ETF", "AI应用": "人工智能ETF",
        "机器人": "机器人ETF", "军工": "军工ETF", "商业航天": "军工ETF", "低空经济": "军工ETF",
        "创新药": "医疗ETF", "CXO": "医疗ETF", "医疗器械": "医疗ETF", "医药": "医疗ETF",
        "券商": "证券ETF", "保险": "沪深300ETF", "银行": "沪深300ETF",
        "白酒消费": "酒ETF", "家电消费": "沪深300ETF", "食品消费": "沪深300ETF",
        "新能源车": "新能源车ETF", "光伏": "光伏ETF", "电力设备": "新能源车ETF",
        "有色金属": "有色金属ETF", "黄金": "黄金ETF", "煤炭": "煤炭ETF", "红利电力": "红利ETF"
    }
}

ETF_FALLBACK = [
    ("sh512760", "芯片ETF"), ("sh512480", "半导体ETF"), ("sh588200", "科创芯片ETF"),
    ("sh515880", "通信ETF"), ("sh515980", "人工智能ETF"), ("sh516820", "机器人ETF"),
    ("sh512170", "医疗ETF"), ("sh512880", "证券ETF"), ("sh512690", "酒ETF"),
    ("sh515030", "新能源车ETF"), ("sh515790", "光伏ETF"), ("sh516510", "云计算ETF"),
    ("sh515400", "大数据ETF"), ("sh512400", "有色金属ETF"), ("sh515220", "煤炭ETF"),
    ("sh510300", "沪深300ETF"), ("sh518880", "黄金ETF"), ("sh510880", "红利ETF"),
    ("sh512660", "军工ETF")
]
INDEX_FALLBACK = [
    ("sh000001", "上证指数"), ("sz399001", "深证成指"), ("sz399006", "创业板指"),
    ("sh000688", "科创50"), ("sh000300", "沪深300"), ("sh000905", "中证500"),
    ("sh000852", "中证1000")
]

@dataclass
class Quote:
    symbol: str
    code: str
    name: str
    price: float = 0.0
    pre_close: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    pct: float = 0.0
    change: float = 0.0
    amount: float = 0.0
    turnover: float = 0.0
    volume_ratio: float = 0.0
    quote_time: str = ""


def log(msg: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {msg}"
    print(line, flush=True)
    with (LOGS / f"run_{datetime.now():%Y%m%d}.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def safe_float(x, default=0.0) -> float:
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return default
        return float(str(x).replace("%", "").replace(",", "").strip())
    except Exception:
        return default


def clamp(x: float, lo=0.0, hi=100.0) -> float:
    return max(lo, min(hi, x))


def read_csv_any(path: Path, **kwargs) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    last = None
    for enc in ENCODINGS:
        try:
            return pd.read_csv(path, encoding=enc, **kwargs)
        except UnicodeDecodeError as e:
            last = e
        except pd.errors.EmptyDataError:
            return pd.DataFrame()
    raise RuntimeError(f"无法读取文件: {path}; {last}")


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
        return DEFAULT_CONFIG.copy()
    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
        merged = DEFAULT_CONFIG.copy()
        merged.update(cfg)
        merged["sector_etf_map"] = {**DEFAULT_CONFIG["sector_etf_map"], **cfg.get("sector_etf_map", {})}
        return merged
    except Exception:
        bad = CONFIG_FILE.with_suffix(f".bad_{datetime.now():%Y%m%d_%H%M%S}.json")
        shutil.copy2(CONFIG_FILE, bad)
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"config.json损坏，已备份为 {bad.name} 并恢复默认配置")
        return DEFAULT_CONFIG.copy()


def ensure_templates() -> None:
    templates = {
        POSITIONS: "code,name,cost,shares,tag\n300394,天孚通信,271,200,hold\n002916,深南电路,403.8,200,hold\n688052,纳芯微,260.8,200,hold\n688120,华海清科,327.26,200,hold\n688525,佰维存储,353.7,200,hold\n688347,华虹公司,360.5,200,hold\n",
        EVENTS: "code,name,hard_bad_news,event_risk,event_boost,note,expire_date\n",
        GLOBAL_MANUAL: "date,item,direction,impact,sector,note\n",
        GLOBAL_AUTO: "date,item,direction,impact,sector,note,source,url\n",
        EVENTS_AUTO: "code,name,hard_bad_news,event_risk,event_boost,note,expire_date,source,url\n",
        TRACK: "recommend_time,code,name,sector,price,signal,market_mode,etf_grade,score,status,last_price,max_return,min_return,days\n",
        DYNAMIC_POOL: "code,name,sector,source,score,add_date,last_seen\n",
        RISK_POOL: "code,name,sector,risk_level,reason,add_date,expire_date\n"
    }
    for p, content in templates.items():
        if not p.exists():
            p.write_text(content, encoding="utf-8-sig")


def symbol(code: str) -> str:
    c = str(code).strip().lower()
    if c.startswith(("sh", "sz", "bj", "hk", "us")):
        return c
    c = re.sub(r"\D", "", c).zfill(6)
    if c.startswith(("4", "8")):
        return "bj" + c
    return ("sh" if c.startswith(("5", "6", "9")) else "sz") + c


def fetch_tencent(symbols: Iterable[str], cfg: dict) -> Dict[str, Quote]:
    syms = list(dict.fromkeys(symbol(s) for s in symbols if str(s).strip()))
    result: Dict[str, Quote] = {}
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://stockapp.finance.qq.com/"}
    timeout = int(cfg["request_timeout"])
    retries = int(cfg["request_retries"])
    for i in range(0, len(syms), 60):
        group = syms[i:i + 60]
        url = "https://qt.gtimg.cn/q=" + ",".join(group)
        text = None
        last_error = None
        for attempt in range(retries):
            try:
                r = requests.get(url, headers=headers, timeout=timeout)
                r.raise_for_status()
                r.encoding = "gbk"
                text = r.text
                break
            except Exception as e:
                last_error = e
                time.sleep(1 + attempt)
        if text is None:
            log(f"行情批次抓取失败，已跳过: {last_error}")
            continue
        for line in text.splitlines():
            m = re.search(r'v_([^=]+)="(.*)";', line)
            if not m:
                continue
            raw_sym = m.group(1).lower()
            p = m.group(2).split("~")
            if len(p) < 40:
                continue
            code = p[2].strip() if len(p) > 2 else raw_sym[-6:]
            q = Quote(
                symbol=raw_sym, code=code, name=p[1].strip(), price=safe_float(p[3]),
                pre_close=safe_float(p[4]), open=safe_float(p[5]), high=safe_float(p[33]),
                low=safe_float(p[34]), pct=safe_float(p[32]), change=safe_float(p[31]),
                amount=safe_float(p[37]), turnover=safe_float(p[38]),
                volume_ratio=safe_float(p[49]) if len(p) > 49 else 0.0,
                quote_time=p[30] if len(p) > 30 else ""
            )
            result[raw_sym] = q
    return result


def load_seed_pool() -> pd.DataFrame:
    df = read_csv_any(SEED_POOL, dtype=str)
    if df.empty:
        raise RuntimeError("stock_pool_seed.csv为空")
    required = {"code", "name", "sector"}
    if not required.issubset(df.columns):
        raise RuntimeError(f"stock_pool_seed.csv必须包含列: {required}")
    df = df[list(required)].copy()
    df["code"] = df["code"].astype(str).str.extract(r"(\d+)")[0].str.zfill(6)
    df = df.dropna(subset=["code"]).drop_duplicates("code")
    return df


def load_positions() -> pd.DataFrame:
    df = read_csv_any(POSITIONS, dtype=str)
    if df.empty:
        return pd.DataFrame(columns=["code", "name", "cost", "shares", "tag"])
    for col in ("code", "name", "cost", "shares", "tag"):
        if col not in df.columns:
            df[col] = ""
    df["code"] = df["code"].astype(str).str.extract(r"(\d+)")[0].str.zfill(6)
    df["cost"] = df["cost"].map(safe_float)
    df["shares"] = df["shares"].map(lambda x: int(safe_float(x)))
    return df.dropna(subset=["code"]).drop_duplicates("code")


def load_market_universe() -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
    df = read_csv_any(MARKET_POOL, dtype=str)
    indexes, etfs = [], []
    if not df.empty and {"secid", "name", "kind"}.issubset(df.columns):
        for _, r in df.iterrows():
            secid = str(r["secid"]).strip()
            code = secid.split(".")[-1].zfill(6)
            sym = ("sh" if secid.startswith("1.") else "sz") + code
            if str(r["kind"]).lower() == "index":
                indexes.append((sym, str(r["name"])))
            elif str(r["kind"]).lower() == "etf":
                etfs.append((sym, str(r["name"])))
    return (indexes or INDEX_FALLBACK), (etfs or ETF_FALLBACK)


def auto_discover(cfg: dict) -> pd.DataFrame:
    """Best-effort Eastmoney discovery. Failure never stops the program."""
    if not cfg.get("use_auto_discovery", True):
        return pd.DataFrame()
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": 1, "pz": 500, "po": 1, "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281", "fltt": 2, "invt": 2,
        "fid": "f6", "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
        "fields": "f12,f14,f2,f3,f6,f8,f15,f16,f17,f18"
    }
    try:
        r = requests.get(url, params=params, timeout=int(cfg["request_timeout"]), headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        diff = r.json().get("data", {}).get("diff", []) or []
        rows = []
        for x in diff:
            code = str(x.get("f12", "")).zfill(6)
            name = str(x.get("f14", ""))
            amount = safe_float(x.get("f6"))
            pct = safe_float(x.get("f3"))
            turnover = safe_float(x.get("f8"))
            if not code or "ST" in name.upper() or amount < 2e8:
                continue
            score = clamp(45 + min(25, math.log10(max(amount, 1)) * 3 - 20) + min(18, max(-8, pct * 2)) + min(12, turnover))
            rows.append({"code": code, "name": name, "sector": "自动发现", "source": "全市场成交额", "score": round(score, 2)})
        return pd.DataFrame(rows).sort_values("score", ascending=False).head(int(cfg["dynamic_pool_max"]))
    except Exception as e:
        log(f"自动发现接口不可用，继续使用核心池与历史动态池: {e}")
        return pd.DataFrame()


def merge_universe(seed: pd.DataFrame, positions: pd.DataFrame, discovered: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    dyn = read_csv_any(DYNAMIC_POOL, dtype=str)
    today = datetime.now().date()
    frames = [seed.assign(source="核心池")]
    if not positions.empty:
        p = positions[["code", "name"]].copy()
        p["sector"] = "当前持仓"
        p["source"] = "持仓"
        frames.append(p)
    if not dyn.empty:
        dyn["last_seen"] = pd.to_datetime(dyn.get("last_seen", dyn.get("add_date", "")), errors="coerce")
        dyn = dyn[(pd.Timestamp(today) - dyn["last_seen"]).dt.days.fillna(999) <= int(cfg["dynamic_keep_days"])]
        frames.append(dyn[["code", "name", "sector"]].assign(source="历史动态池"))
    if not discovered.empty:
        frames.append(discovered[["code", "name", "sector"]].assign(source="今日自动发现"))
    x = pd.concat(frames, ignore_index=True)
    x["code"] = x["code"].astype(str).str.extract(r"(\d+)")[0].str.zfill(6)
    x = x.dropna(subset=["code"]).drop_duplicates("code", keep="first")
    seed_sector = seed.set_index("code")["sector"].to_dict()
    x["sector"] = x.apply(lambda r: seed_sector.get(r["code"], r["sector"]), axis=1)
    return x


def build_quote_frames(universe: pd.DataFrame, cfg: dict):
    indexes, etfs = load_market_universe()
    syms = [symbol(c) for c in universe["code"]] + [s for s, _ in indexes] + [s for s, _ in etfs]
    quotes = fetch_tencent(syms, cfg)
    stock_rows = []
    for _, r in universe.iterrows():
        q = quotes.get(symbol(r["code"]))
        if not q or q.price <= 0:
            continue
        stock_rows.append({
            "code": r["code"], "name": r["name"] or q.name, "sector": r["sector"], "source": r["source"],
            "price": q.price, "pct": q.pct, "open": q.open, "high": q.high, "low": q.low,
            "pre_close": q.pre_close, "amount": q.amount, "turnover": q.turnover,
            "volume_ratio": q.volume_ratio, "quote_time": q.quote_time,
            "close_location": (q.price - q.low) / (q.high - q.low) if q.high > q.low else 0.5,
            "high_dist": (q.price / q.high - 1) * 100 if q.high else 0,
            "low_rebound": (q.price / q.low - 1) * 100 if q.low else 0,
            "price_vs_open": (q.price / q.open - 1) * 100 if q.open else 0
        })
    stock_df = pd.DataFrame(stock_rows)

    def simple(pool, kind):
        rows = []
        for s, n in pool:
            q = quotes.get(s)
            if not q or q.price <= 0:
                continue
            rows.append({"kind": kind, "symbol": s, "code": q.code, "name": n, "price": q.price,
                         "pct": q.pct, "open": q.open, "high": q.high, "low": q.low,
                         "pre_close": q.pre_close, "amount": q.amount, "quote_time": q.quote_time,
                         "close_location": (q.price-q.low)/(q.high-q.low) if q.high > q.low else .5})
        return pd.DataFrame(rows)
    return stock_df, simple(indexes, "index"), simple(etfs, "etf")


def load_etf_history() -> pd.DataFrame:
    files = sorted(HISTORY.glob("etf_*.csv"))[-20:]
    rows = []
    for f in files:
        try:
            d = read_csv_any(f)
            if not d.empty:
                d["date"] = f.stem.replace("etf_", "")[:8]
                rows.append(d)
        except Exception:
            pass
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def score_etfs(etf: pd.DataFrame, stock: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    if etf.empty:
        return etf
    hist = load_etf_history()
    sector_map = cfg["sector_etf_map"]
    reverse: Dict[str, List[str]] = {}
    for sec, etf_name in sector_map.items():
        reverse.setdefault(etf_name, []).append(sec)
    rows = []
    for _, r in etf.iterrows():
        name = r["name"]
        h = hist[hist["name"] == name].copy() if not hist.empty and "name" in hist.columns else pd.DataFrame()
        past = list(h["price"].map(safe_float))[-10:] if not h.empty else []
        peak = max(past + [r["price"]]) if past else r["high"] or r["price"]
        drawdown = (r["price"] / peak - 1) * 100 if peak else 0
        trend = 50 + r["pct"] * 5 + (r["close_location"] - .5) * 30
        if len(past) >= 3:
            ma3 = mean(past[-3:])
            trend += 10 if r["price"] >= ma3 else -10
        if len(past) >= 8:
            ma8 = mean(past[-8:])
            trend += 12 if r["price"] >= ma8 else -12
        sectors = reverse.get(name, [])
        subset = stock[stock["sector"].isin(sectors)] if sectors else pd.DataFrame()
        breadth = (subset["pct"] > 0).mean() * 100 if not subset.empty else 50
        median_pct = subset["pct"].median() if not subset.empty else r["pct"]
        relative = r["pct"] - etf["pct"].median()
        score = clamp(trend * .42 + breadth * .28 + clamp(50 + relative * 8) * .18 + clamp(50 + median_pct * 6) * .12)
        grade = "S" if score >= 82 else "A" if score >= 70 else "B" if score >= 58 else "C" if score >= 45 else "D" if score >= 30 else "E"
        alert = "正常"
        dd = abs(min(0, drawdown))
        if dd >= cfg["industry_alert_drawdown_red"] or (grade == "E" and r["pct"] <= -3):
            alert = "红色：全球/行业共振回撤，停止新增，反弹优先减弱"
        elif dd >= cfg["industry_alert_drawdown_orange"] or grade == "D":
            alert = "橙色：趋势破坏，暂停新开仓"
        elif dd >= cfg["industry_alert_drawdown_yellow"] or grade == "C":
            alert = "黄色：高位降温，停止追高"
        rows.append({**r.to_dict(), "etf_score": round(score, 2), "grade": grade, "breadth": round(breadth, 1),
                     "median_stock_pct": round(median_pct, 2), "relative_strength": round(relative, 2),
                     "drawdown_from_recent_peak": round(drawdown, 2), "alert": alert})
    return pd.DataFrame(rows).sort_values(["etf_score", "pct"], ascending=False)


def global_risk_score(cfg: dict) -> Tuple[float, List[str]]:
    frames = [read_csv_any(GLOBAL_AUTO), read_csv_any(GLOBAL_MANUAL)]
    frames = [x for x in frames if not x.empty]
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    score = 25.0
    notes = []
    if not df.empty:
        today = datetime.now().date()
        seen = set()
        for _, r in df.iterrows():
            try:
                d = pd.to_datetime(r.get("date"), errors="coerce")
                if pd.isna(d):
                    continue
                age = (today - d.date()).days
                if age < 0 or age > 14:
                    continue
                item = str(r.get("item", "事件")).strip()
                key = re.sub(r"\W+", "", item.lower())[:48]
                if key and key in seen:
                    continue
                seen.add(key)
                impact = safe_float(r.get("impact"))
                direction = str(r.get("direction", "risk")).lower()
                decay = math.exp(-age / 4.0)
                signed = abs(impact) * decay * (1 if direction in {"risk", "negative", "-", "利空"} else -1)
                score += signed
                notes.append(f"{item}({signed:+.1f}) {r.get('note','')}")
            except Exception:
                continue
    return round(clamp(score), 1), notes[:12]


def market_regime(index_df: pd.DataFrame, stock: pd.DataFrame, etf_scores: pd.DataFrame, global_risk: float, cfg: dict):
    if stock.empty:
        return "数据不足", 100.0, 0.0, ["股票行情为空"]
    up_ratio = (stock["pct"] > 0).mean() * 100
    avg_pct = stock["pct"].mean()
    severe_down = (stock["pct"] <= -5).mean() * 100
    strong_etf = (etf_scores["grade"].isin(["S", "A"])).sum() if not etf_scores.empty else 0
    weak_etf = (etf_scores["grade"].isin(["D", "E"])).sum() if not etf_scores.empty else 0
    idx_pct = index_df["pct"].mean() if not index_df.empty else avg_pct
    risk = 50 - (up_ratio - 50) * .55 - avg_pct * 7 - idx_pct * 5 + severe_down * .8 + weak_etf * 2.5 - strong_etf * 1.5
    risk = risk * (1 - cfg["international_weight"]) + global_risk * cfg["international_weight"]
    risk = clamp(risk)
    if risk >= cfg["market_extreme_block"]:
        mode = "极端风险日"
    elif risk >= cfg["market_risk_block"]:
        mode = "风险日"
    elif idx_pct > .5 and up_ratio > 58 and strong_etf >= 3:
        mode = "强势进攻日"
    elif idx_pct > 0 and strong_etf >= 1:
        mode = "普通轮动日"
    elif idx_pct > 0 and up_ratio < 55:
        mode = "弱势反弹日"
    else:
        mode = "防守观察日"
    allowed = 0 if risk >= cfg["market_extreme_block"] else 20 if risk >= cfg["market_risk_block"] else 40 if risk >= 55 else 60 if risk >= 40 else 80
    reasons = [f"上涨家数比例 {up_ratio:.1f}%", f"样本平均涨跌 {avg_pct:.2f}%", f"指数均值 {idx_pct:.2f}%",
               f"强ETF {strong_etf}只", f"弱ETF {weak_etf}只", f"全球风险 {global_risk:.1f}"]
    return mode, round(risk, 1), allowed, reasons


def load_event_map() -> Dict[str, dict]:
    frames = [read_csv_any(EVENTS_AUTO, dtype=str), read_csv_any(EVENTS, dtype=str)]
    frames = [x for x in frames if not x.empty]
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    out: Dict[str, dict] = {}
    if df.empty:
        return out
    today = datetime.now().date()
    for _, r in df.iterrows():
        code = str(r.get("code", "")).strip().zfill(6)
        exp = pd.to_datetime(r.get("expire_date", ""), errors="coerce")
        if not pd.isna(exp) and exp.date() < today:
            continue
        cur = out.setdefault(code, {"bad": False, "risk": 0.0, "boost": 0.0, "notes": []})
        cur["bad"] = cur["bad"] or str(r.get("hard_bad_news", "0")).lower() in {"1", "true", "yes", "是"}
        cur["risk"] += safe_float(r.get("event_risk"))
        cur["boost"] += safe_float(r.get("event_boost"))
        note = str(r.get("note", "")).strip()
        if note and note not in cur["notes"]:
            cur["notes"].append(note)
    for v in out.values():
        v["risk"] = min(35.0, v["risk"])
        v["boost"] = min(20.0, v["boost"])
        v["note"] = "；".join(v.pop("notes"))[:240]
    return out


def score_stocks(stock: pd.DataFrame, etfs: pd.DataFrame, positions: pd.DataFrame, mode: str, market_risk: float, cfg: dict) -> pd.DataFrame:
    etf_map = cfg["sector_etf_map"]
    etf_lookup = etfs.set_index("name").to_dict("index") if not etfs.empty else {}
    pos_map = positions.set_index("code").to_dict("index") if not positions.empty else {}
    events = load_event_map()
    rows = []
    for _, r in stock.iterrows():
        ev = events.get(r["code"], {"bad": False, "risk": 0, "boost": 0, "note": ""})
        etf_name = etf_map.get(r["sector"], "")
        e = etf_lookup.get(etf_name, {})
        etf_score = safe_float(e.get("etf_score"), 50)
        etf_grade = str(e.get("grade", "C"))
        etf_pct = safe_float(e.get("pct"), 0)
        rel = r["pct"] - etf_pct
        quality = 50
        quality += 14 if r["source"] in {"核心池", "持仓"} else 2
        quality += min(10, math.log10(max(r["amount"], 1)) * 2 - 8)
        quality += ev["boost"] - ev["risk"]
        trend = 48 + rel * 6 + (r["close_location"] - .5) * 38 + r["price_vs_open"] * 3
        trend += 10 if .75 <= r["volume_ratio"] <= 2.5 else -5 if r["volume_ratio"] > 4 else 0
        trend += 8 if r["high_dist"] >= -1.8 else 0
        trend -= 18 if r["pct"] >= cfg["max_chase_pct"] else 0
        quick = trend * .46 + etf_score * .34 + quality * .20
        if mode == "强势进攻日":
            quick += 7
        elif mode == "普通轮动日":
            quick += 2
        elif mode in {"风险日", "极端风险日"}:
            quick -= 20
        elif mode == "弱势反弹日":
            quick -= 8
        quick = clamp(quick)
        oversold = 0.0
        if r["pct"] <= -4.5:
            confirm = r["low_rebound"] >= 2 and r["close_location"] >= .55 and rel >= -1
            oversold = clamp(42 + abs(r["pct"]) * 3 + etf_score * .18 + quality * .16 + (18 if confirm else -12) - market_risk * .12)
        held = r["code"] in pos_map
        cost = safe_float(pos_map.get(r["code"], {}).get("cost"), 0)
        pnl = (r["price"] / cost - 1) * 100 if held and cost else 0
        blocked = ev["bad"] or etf_grade in {"D", "E"} or market_risk >= cfg["market_extreme_block"]
        signal, action = "回避", "当前无优势"
        if ev["bad"]:
            signal, action = "禁止买入", "重大利空；若持有，反弹优先退出"
        elif held:
            if etf_grade in {"D", "E"} and rel < 0:
                signal, action = "持仓减法", "行业弱且个股更弱；反弹优先减1手"
            elif quick >= cfg["quick_profit_min_score"] and etf_grade in {"S", "A"}:
                signal, action = "核心保留", "相对强，继续持有；不因刚回本机械全卖"
            elif rel < -2 or r["pct"] <= -5:
                signal, action = "持仓观察", "暂不补仓；等待反弹质量再决定"
            else:
                signal, action = "持仓保留", "继续观察，弱于ETF时再降仓"
        elif not blocked and quick >= cfg["quick_profit_min_score"] and etf_score >= cfg["etf_buy_min_score"]:
            signal, action = "快吃肉候选", "仅小仓1手；尾盘确认后介入"
        elif not blocked and quick >= cfg["stock_buy_min_score"] and etf_score >= cfg["etf_buy_min_score"]:
            signal, action = "趋势候选", "强ETF中的强股，可小仓等待回踩"
        elif oversold >= cfg["oversold_min_score"] and etf_grade not in {"D", "E"} and market_risk < cfg["market_risk_block"]:
            signal, action = "超跌试仓", "仅1手，必须有回拉确认"
        elif etf_grade in {"D", "E"}:
            signal, action = "行业禁买", f"{etf_name or r['sector']}为{etf_grade}级，停止新增"
        score = max(quick, oversold)
        rows.append({**r.to_dict(), "etf_name": etf_name, "etf_grade": etf_grade, "etf_score": round(etf_score, 2),
                     "relative_strength": round(rel, 2), "quality_score": round(clamp(quality), 2),
                     "quick_profit_score": round(quick, 2), "oversold_score": round(oversold, 2),
                     "held": held, "cost": cost, "position_pnl": round(pnl, 2), "event_note": ev["note"],
                     "signal": signal, "action": action, "final_score": round(score, 2)})
    out = pd.DataFrame(rows)
    priority = {"快吃肉候选": 9, "趋势候选": 8, "超跌试仓": 7, "核心保留": 6, "持仓保留": 5,
                "持仓观察": 4, "持仓减法": 3, "行业禁买": 1, "回避": 0, "禁止买入": -1}
    out["priority"] = out["signal"].map(priority).fillna(0)
    return out.sort_values(["priority", "final_score"], ascending=False)


def update_dynamic_pool(scored: pd.DataFrame, cfg: dict) -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    candidates = scored[(scored["final_score"] >= 65) & (~scored["signal"].isin(["行业禁买", "禁止买入", "回避"]))].copy()
    candidates = candidates.head(int(cfg["dynamic_pool_max"]))
    new = pd.DataFrame({
        "code": candidates["code"], "name": candidates["name"], "sector": candidates["sector"],
        "source": candidates["signal"], "score": candidates["final_score"], "add_date": today, "last_seen": today
    })
    old = read_csv_any(DYNAMIC_POOL, dtype=str)
    all_df = pd.concat([new, old], ignore_index=True) if not old.empty else new
    if not all_df.empty:
        all_df = all_df.drop_duplicates("code", keep="first")
        write_csv(all_df.head(int(cfg["dynamic_pool_max"])), DYNAMIC_POOL)


def update_risk_pool(scored: pd.DataFrame, etfs: pd.DataFrame, cfg: dict) -> None:
    today = datetime.now().date()
    rows = []
    alert_map = etfs.set_index("name")["alert"].to_dict() if not etfs.empty else {}
    for _, r in scored.iterrows():
        if r["signal"] in {"持仓减法", "行业禁买", "禁止买入"}:
            level = "红" if r["signal"] == "禁止买入" else "橙"
            rows.append({"code": r["code"], "name": r["name"], "sector": r["sector"], "risk_level": level,
                         "reason": r["action"] + "；" + alert_map.get(r["etf_name"], ""),
                         "add_date": str(today), "expire_date": str(today + timedelta(days=int(cfg["risk_keep_days"])))})
    write_csv(pd.DataFrame(rows, columns=["code","name","sector","risk_level","reason","add_date","expire_date"]), RISK_POOL)


def update_tracking(scored: pd.DataFrame, mode: str, cfg: dict) -> pd.DataFrame:
    hist = read_csv_any(TRACK, dtype=str)
    if hist.empty:
        hist = pd.DataFrame(columns=["recommend_time","code","name","sector","price","signal","market_mode","etf_grade","score","status","last_price","max_return","min_return","days"])
    price_map = scored.set_index("code")["price"].to_dict()
    today = datetime.now()
    for i, r in hist.iterrows():
        code = str(r["code"]).zfill(6)
        if code not in price_map:
            continue
        start = safe_float(r["price"])
        current = safe_float(price_map[code])
        ret = (current / start - 1) * 100 if start else 0
        hist.at[i, "last_price"] = current
        hist.at[i, "max_return"] = max(safe_float(r.get("max_return"), ret), ret)
        hist.at[i, "min_return"] = min(safe_float(r.get("min_return"), ret), ret)
        dt = pd.to_datetime(r["recommend_time"], errors="coerce")
        days = max(0, (today.date() - dt.date()).days) if not pd.isna(dt) else 0
        hist.at[i, "days"] = days
        if days >= 5 and str(r.get("status", "open")) == "open":
            hist.at[i, "status"] = "win" if ret > 0 else "loss"
    existing_open = set(hist.loc[hist["status"] == "open", "code"].astype(str).str.zfill(6))
    add = scored[(~scored["held"]) & scored["signal"].isin(["快吃肉候选", "趋势候选", "超跌试仓"])].head(int(cfg["recommend_max"]))
    new_rows = []
    for _, r in add.iterrows():
        if r["code"] in existing_open:
            continue
        new_rows.append({"recommend_time": today.strftime("%Y-%m-%d %H:%M:%S"), "code": r["code"], "name": r["name"],
                         "sector": r["sector"], "price": r["price"], "signal": r["signal"], "market_mode": mode,
                         "etf_grade": r["etf_grade"], "score": r["final_score"], "status": "open",
                         "last_price": r["price"], "max_return": 0, "min_return": 0, "days": 0})
    if new_rows:
        hist = pd.concat([pd.DataFrame(new_rows), hist], ignore_index=True)
    write_csv(hist, TRACK)
    return hist


def html_table(df: pd.DataFrame, cols: List[str], limit=30) -> str:
    if df.empty:
        return '<div class="empty">无</div>'
    use = [c for c in cols if c in df.columns]
    return df[use].head(limit).to_html(index=False, classes="data", border=0)


def render_html(now, mode, risk, allowed, reasons, global_notes, index_df, etfs, scored, tracking, cfg):
    buys = scored[(~scored["held"]) & scored["signal"].isin(["快吃肉候选", "趋势候选", "超跌试仓"])].head(int(cfg["recommend_max"]))
    held = scored[scored["held"]]
    alerts = etfs[etfs["alert"] != "正常"] if not etfs.empty else pd.DataFrame()
    mode_class = "danger" if risk >= cfg["market_risk_block"] else "warn" if risk >= 50 else "ok"
    css = """
    <style>
    body{font-family:-apple-system,BlinkMacSystemFont,'Microsoft YaHei',Arial;margin:0;background:#f3f6fa;color:#1f2328}
    .wrap{max-width:1500px;margin:auto;padding:16px}.hero{padding:18px;border-radius:14px;background:white;box-shadow:0 2px 10px #00000012}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:14px 0}.card{background:#fff;border-radius:12px;padding:14px;box-shadow:0 2px 10px #0000000d}
    .big{font-size:28px;font-weight:700}.ok{color:#16794b}.warn{color:#a15c00}.danger{color:#c62828}
    h1{margin:0 0 8px}h2{margin-top:24px}.data{border-collapse:collapse;width:100%;background:#fff;font-size:13px}.data th{position:sticky;top:0;background:#1769aa;color:#fff;padding:8px}.data td{padding:7px;border-bottom:1px solid #e6e8eb;text-align:center}.data tr:hover{background:#f4f8ff}.empty{background:#fff;padding:18px;border-radius:10px}.note{font-size:13px;color:#57606a}.scroll{overflow-x:auto}.pill{display:inline-block;padding:3px 9px;border-radius:12px;background:#eaf2ff;margin:2px}.alert{border-left:5px solid #d97706}
    </style>
    """
    summary = "；".join(reasons)
    notes = "；".join(global_notes) if global_notes else "未录入新的国际事件；当前以市场价格行为为主"
    return f"""<!DOCTYPE html><html lang='zh-CN'><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>V5智能决策</title>{css}</head><body><div class='wrap'>
    <div class='hero'><h1>V5 市场状态 + ETF轮动 + 动态股票池</h1><div class='note'>生成时间：{now:%Y-%m-%d %H:%M:%S}</div>
    <div class='grid'><div class='card'><div>市场模式</div><div class='big {mode_class}'>{mode}</div></div><div class='card'><div>综合风险</div><div class='big {mode_class}'>{risk}/100</div></div><div class='card'><div>建议最高仓位</div><div class='big'>{allowed}%</div></div><div class='card'><div>今日新开仓</div><div class='big'>{len(buys)}只</div></div></div>
    <div class='note'>{summary}</div><div class='note'>国际事件：{notes}</div></div>
    <h2>今日允许关注</h2><div class='scroll'>{html_table(buys,['signal','code','name','sector','price','pct','etf_name','etf_grade','etf_score','relative_strength','quick_profit_score','oversold_score','action'],10)}</div>
    <h2>持仓决策</h2><div class='scroll'>{html_table(held,['signal','code','name','sector','price','cost','position_pnl','pct','etf_name','etf_grade','relative_strength','final_score','action'],30)}</div>
    <h2>行业ETF强弱与回撤提醒</h2><div class='scroll'>{html_table(etfs,['name','price','pct','etf_score','grade','breadth','relative_strength','drawdown_from_recent_peak','alert'],30)}</div>
    <h2>行业风险提醒</h2><div class='scroll'>{html_table(alerts,['name','pct','grade','drawdown_from_recent_peak','alert'],30)}</div>
    <h2>指数</h2><div class='scroll'>{html_table(index_df,['name','price','pct','amount','quote_time'],20)}</div>
    <h2>推荐跟踪</h2><div class='scroll'>{html_table(tracking,['recommend_time','code','name','signal','market_mode','etf_grade','score','price','last_price','max_return','min_return','days','status'],30)}</div>
    <h2>全部评分前50</h2><div class='scroll'>{html_table(scored,['signal','code','name','sector','price','pct','etf_grade','etf_score','relative_strength','quality_score','quick_profit_score','oversold_score','final_score','action'],50)}</div>
    </div></body></html>"""


def cleanup(cfg: dict) -> None:
    cutoff = datetime.now() - timedelta(days=int(cfg["history_keep_days"]))
    for p in HISTORY.iterdir():
        try:
            if datetime.fromtimestamp(p.stat().st_mtime) < cutoff:
                p.unlink()
        except Exception:
            pass


def run() -> int:
    ensure_templates()
    cfg = load_config()
    now = datetime.now()
    log("V5.1 AutoRisk开始运行")
    seed = load_seed_pool()
    positions = load_positions()
    discovered = auto_discover(cfg)
    universe = merge_universe(seed, positions, discovered, cfg)
    log(f"股票池：核心{len(seed)}，持仓{len(positions)}，自动发现{len(discovered)}，合并后{len(universe)}")
    stock, index_df, etf_df = build_quote_frames(universe, cfg)
    if stock.empty:
        raise RuntimeError("未取得任何股票行情。请检查网络、防火墙或稍后重试。")
    etfs = score_etfs(etf_df, stock, cfg)
    global_risk, global_notes = global_risk_score(cfg)
    mode, risk, allowed, reasons = market_regime(index_df, stock, etfs, global_risk, cfg)
    scored = score_stocks(stock, etfs, positions, mode, risk, cfg)
    update_dynamic_pool(scored, cfg)
    update_risk_pool(scored, etfs, cfg)
    tracking = update_tracking(scored, mode, cfg)

    stamp = now.strftime("%Y%m%d_%H%M%S")
    write_csv(stock, OUT / "market_snapshot.csv")
    write_csv(index_df, OUT / "index_snapshot.csv")
    write_csv(etfs, OUT / "etf_rotation.csv")
    write_csv(scored, OUT / "all_scores.csv")
    write_csv(scored[(~scored["held"]) & scored["signal"].isin(["快吃肉候选","趋势候选","超跌试仓"])].head(int(cfg["recommend_max"])), OUT / "buy_candidates.csv")
    write_csv(scored[scored["held"]], OUT / "position_decisions.csv")
    write_csv(etf_df, HISTORY / f"etf_{now:%Y%m%d}.csv")
    write_csv(scored, HISTORY / f"scores_{stamp}.csv")

    html = render_html(now, mode, risk, allowed, reasons, global_notes, index_df, etfs, scored, tracking, cfg)
    latest = OUT / "mobile_latest.html"
    latest.write_text(html, encoding="utf-8")
    (HISTORY / f"decision_{stamp}.html").write_text(html, encoding="utf-8")
    txt = [f"生成时间：{now:%Y-%m-%d %H:%M:%S}", f"市场模式：{mode}", f"风险：{risk}/100", f"建议最高仓位：{allowed}%", "", "【新开仓】"]
    buys = scored[(~scored["held"]) & scored["signal"].isin(["快吃肉候选","趋势候选","超跌试仓"])].head(int(cfg["recommend_max"]))
    txt += ["无"] if buys.empty else [f"{r['name']}｜{r['signal']}｜ETF {r['etf_grade']}｜分数{r['final_score']}｜{r['action']}" for _,r in buys.iterrows()]
    txt += ["", "【持仓】"]
    held = scored[scored["held"]]
    txt += ["无"] if held.empty else [f"{r['name']}｜盈亏{r['position_pnl']:.2f}%｜{r['signal']}｜{r['action']}" for _,r in held.iterrows()]
    (OUT / "latest_decision.txt").write_text("\n".join(txt), encoding="utf-8-sig")
    cleanup(cfg)
    log(f"运行完成：{latest}")
    if cfg.get("auto_open_html") and os.name == "nt":
        os.startfile(latest)  # type: ignore[attr-defined]
    return 0


def main() -> None:
    try:
        code = run()
    except KeyboardInterrupt:
        log("用户中止")
        code = 130
    except Exception as e:
        err = traceback.format_exc()
        log(f"运行失败：{e}")
        (LOGS / "last_error.txt").write_text(err, encoding="utf-8")
        print("\n详细错误已写入 logs\\last_error.txt", flush=True)
        code = 1
    sys.exit(code)


if __name__ == "__main__":
    main()
