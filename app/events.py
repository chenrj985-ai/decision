from __future__ import annotations

from datetime import datetime
from typing import Dict

import pandas as pd

from .paths import EVENTS, EVENTS_AUTO
from .utils import read_csv_any, safe_float


def load_event_map() -> Dict[str, dict]:
    frames = [
        read_csv_any(EVENTS_AUTO, dtype=str),
        read_csv_any(EVENTS, dtype=str)
    ]
    frames = [df for df in frames if not df.empty]
    if not frames:
        return {}

    df = pd.concat(frames, ignore_index=True)
    today = datetime.now().date()
    output: Dict[str, dict] = {}

    for _, row in df.iterrows():
        code = str(row.get("code", "")).strip().zfill(6)
        if not code.strip("0"):
            continue

        expire = pd.to_datetime(row.get("expire_date", ""), errors="coerce")
        if not pd.isna(expire) and expire.date() < today:
            continue

        current = output.setdefault(
            code,
            {"bad": False, "risk": 0.0, "boost": 0.0, "notes": []}
        )
        current["bad"] = (
            current["bad"]
            or str(row.get("hard_bad_news", "0")).lower()
            in {"1", "true", "yes", "是"}
        )
        current["risk"] += safe_float(row.get("event_risk"))
        current["boost"] += safe_float(row.get("event_boost"))

        note = str(row.get("note", "")).strip()
        if note and note not in current["notes"]:
            current["notes"].append(note)

    for item in output.values():
        item["risk"] = min(35.0, item["risk"])
        item["boost"] = min(20.0, item["boost"])
        item["note"] = "；".join(item.pop("notes"))[:240]

    return output
