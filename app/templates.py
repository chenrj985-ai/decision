from __future__ import annotations

from .paths import (
    POSITIONS, EVENTS, EVENTS_AUTO, GLOBAL_MANUAL, GLOBAL_AUTO,
    TRACK, DYNAMIC_POOL, RISK_POOL
)


def ensure_templates() -> None:
    templates = {
        POSITIONS:
            "code,name,cost,shares,tag\n"
            "600536,中国软件,0,200,hold\n",
        EVENTS:
            "code,name,hard_bad_news,event_risk,event_boost,note,expire_date\n",
        EVENTS_AUTO:
            "code,name,hard_bad_news,event_risk,event_boost,note,expire_date,source,url\n",
        GLOBAL_MANUAL:
            "date,item,direction,impact,sector,note\n",
        GLOBAL_AUTO:
            "date,item,direction,impact,sector,note,source,url\n",
        TRACK:
            "recommend_time,code,name,sector,price,signal,market_mode,"
            "etf_grade,score,status,last_price,max_return,min_return,days\n",
        DYNAMIC_POOL:
            "code,name,sector,source,score,add_date,last_seen\n",
        RISK_POOL:
            "code,name,sector,risk_level,reason,add_date,expire_date\n"
    }
    for path, content in templates.items():
        if not path.exists():
            path.write_text(content, encoding="utf-8-sig")
