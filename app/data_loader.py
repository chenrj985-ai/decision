from __future__ import annotations

from datetime import datetime
from typing import List, Tuple

import pandas as pd

from .paths import SEED_POOL, MARKET_POOL, POSITIONS, DYNAMIC_POOL
from .utils import read_csv_any, safe_float

INDEX_FALLBACK = [
    ("sh000001", "上证指数"),
    ("sz399001", "深证成指"),
    ("sz399006", "创业板指"),
    ("sh000688", "科创50"),
    ("sh000300", "沪深300"),
    ("sh000905", "中证500"),
    ("sh000852", "中证1000")
]

ETF_FALLBACK = [
    ("sh512760", "芯片ETF"),
    ("sh512480", "半导体ETF"),
    ("sh588200", "科创芯片ETF"),
    ("sh515880", "通信ETF"),
    ("sh515980", "人工智能ETF"),
    ("sh516820", "机器人ETF"),
    ("sh512170", "医疗ETF"),
    ("sh512880", "证券ETF"),
    ("sh512690", "酒ETF"),
    ("sh515030", "新能源车ETF"),
    ("sh515790", "光伏ETF"),
    ("sh516510", "云计算ETF"),
    ("sh515400", "大数据ETF"),
    ("sh512400", "有色金属ETF"),
    ("sh515220", "煤炭ETF"),
    ("sh510300", "沪深300ETF"),
    ("sh518880", "黄金ETF"),
    ("sh510880", "红利ETF"),
    ("sh512660", "军工ETF")
]


def load_seed_pool() -> pd.DataFrame:
    df = read_csv_any(SEED_POOL, dtype=str)
    if df.empty:
        raise RuntimeError("data\\stock_pool_seed.csv为空")
    required = {"code", "name", "sector"}
    if not required.issubset(df.columns):
        raise RuntimeError(f"核心池必须包含列：{sorted(required)}")
    df = df[["code", "name", "sector"]].copy()
    df["code"] = df["code"].astype(str).str.extract(r"(\d+)")[0].str.zfill(6)
    return df.dropna(subset=["code"]).drop_duplicates("code")


def load_positions() -> pd.DataFrame:
    df = read_csv_any(POSITIONS, dtype=str)
    columns = ["code", "name", "cost", "shares", "tag"]
    if df.empty:
        return pd.DataFrame(columns=columns)
    for col in columns:
        if col not in df.columns:
            df[col] = ""
    df = df[columns].copy()
    df["code"] = df["code"].astype(str).str.extract(r"(\d+)")[0].str.zfill(6)
    df["cost"] = df["cost"].map(safe_float)
    df["shares"] = df["shares"].map(lambda x: int(safe_float(x)))
    return df.dropna(subset=["code"]).drop_duplicates("code")


def load_market_universe() -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
    df = read_csv_any(MARKET_POOL, dtype=str)
    indexes, etfs = [], []
    if not df.empty and {"secid", "name", "kind"}.issubset(df.columns):
        for _, row in df.iterrows():
            secid = str(row["secid"]).strip()
            code = secid.split(".")[-1].zfill(6)
            prefix = "sh" if secid.startswith("1.") else "sz"
            item = (prefix + code, str(row["name"]))
            if str(row["kind"]).lower() == "index":
                indexes.append(item)
            elif str(row["kind"]).lower() == "etf":
                etfs.append(item)
    return indexes or INDEX_FALLBACK, etfs or ETF_FALLBACK


def merge_universe(
    seed: pd.DataFrame,
    positions: pd.DataFrame,
    discovered: pd.DataFrame,
    config: dict
) -> pd.DataFrame:
    frames = [seed.assign(source="核心池")]
    if not positions.empty:
        pos = positions[["code", "name"]].copy()
        pos["sector"] = "当前持仓"
        pos["source"] = "持仓"
        frames.append(pos)

    dynamic = read_csv_any(DYNAMIC_POOL, dtype=str)
    if not dynamic.empty:
        dynamic["last_seen"] = pd.to_datetime(
            dynamic.get("last_seen", dynamic.get("add_date", "")),
            errors="coerce"
        )
        age = (pd.Timestamp(datetime.now().date()) - dynamic["last_seen"]).dt.days
        dynamic = dynamic[age.fillna(999) <= int(config["dynamic_keep_days"])]
        if not dynamic.empty:
            frames.append(
                dynamic[["code", "name", "sector"]]
                .assign(source="历史动态池")
            )

    if not discovered.empty:
        frames.append(
            discovered[["code", "name", "sector"]]
            .assign(source="今日自动发现")
        )

    merged = pd.concat(frames, ignore_index=True)
    merged["code"] = (
        merged["code"].astype(str).str.extract(r"(\d+)")[0].str.zfill(6)
    )
    merged = merged.dropna(subset=["code"]).drop_duplicates("code", keep="first")
    seed_sector = seed.set_index("code")["sector"].to_dict()
    merged["sector"] = merged.apply(
        lambda r: seed_sector.get(r["code"], r["sector"]), axis=1
    )
    return merged
