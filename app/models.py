from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict


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

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
