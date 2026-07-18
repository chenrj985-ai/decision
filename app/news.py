from __future__ import annotations

import html
import re
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote
import xml.etree.ElementTree as ET

import requests

from .utils import ROOT, load_json, now_cn, save_json

KEYWORDS = {
    "地缘冲突": ["war", "conflict", "missile", "sanction", "战争", "制裁"],
    "贸易科技": ["tariff", "export control", "chip ban", "关税", "出口管制"],
    "流动性": ["rate hike", "inflation", "fed", "加息", "通胀"],
    "供应链": ["earthquake", "fire", "outage", "shortage", "地震", "火灾", "停产"],
}


def _risk_score(title: str) -> tuple[int, str]:
    low = title.lower()
    best = (0, "一般")
    for tag, words in KEYWORDS.items():
        hits = sum(1 for w in words if w.lower() in low)
        if hits:
            best = max(best, (min(30, 10 + hits * 6), tag))
    return best


def fetch_news(timeout: int = 15, cache_hours: int = 6) -> dict:
    cache = ROOT / "cache/news.json"
    old = load_json(cache, {}) or {}
    try:
        if old.get("fetched_at"):
            age = now_cn() - __import__("datetime").datetime.fromisoformat(old["fetched_at"])
            if age < timedelta(hours=cache_hours):
                old["source"] = "cache"
                return old
    except Exception:
        pass

    query = quote("global markets semiconductor AI stocks when:1d")
    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    items = []
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 StockDecisionV6"})
        r.raise_for_status()
        root = ET.fromstring(r.content)
        for node in root.findall(".//item")[:30]:
            title = html.unescape(node.findtext("title") or "").strip()
            link = node.findtext("link") or ""
            title = re.sub(r"\s+-\s+[^-]+$", "", title)
            score, tag = _risk_score(title)
            items.append({"title": title, "link": link, "risk": score, "tag": tag})
        items.sort(key=lambda x: x["risk"], reverse=True)
        result = {"fetched_at": now_cn().isoformat(), "source": "google_news", "items": items[:15]}
        save_json(cache, result)
        return result
    except Exception as exc:
        if old:
            old["source"] = "stale_cache"
            old["warning"] = str(exc)
            return old
        return {"fetched_at": now_cn().isoformat(), "source": "unavailable", "items": [], "warning": str(exc)}
