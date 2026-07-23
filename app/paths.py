from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
OUTPUT = BASE / "output"
HISTORY = OUTPUT / "history"
LOGS = BASE / "logs"

CONFIG_FILE = BASE / "config.json"
SEED_POOL = DATA / "stock_pool_seed.csv"
MARKET_POOL = DATA / "market_pool.csv"
POSITIONS = DATA / "my_positions.csv"
DYNAMIC_POOL = DATA / "dynamic_pool.csv"
RISK_POOL = DATA / "risk_pool.csv"
EVENTS = DATA / "event_risk.csv"
EVENTS_AUTO = DATA / "event_risk_auto.csv"
GLOBAL_MANUAL = DATA / "global_risk_manual.csv"
GLOBAL_AUTO = DATA / "global_risk_auto.csv"
TRACK = DATA / "recommendation_history.csv"
QUOTE_CACHE = DATA / "quote_cache.csv"
SOURCE_HEALTH = OUTPUT / "source_health.json"
DISCOVERY_CACHE = DATA / "auto_discovery_cache.csv"
DISCOVERY_HEALTH = OUTPUT / "discovery_health.json"

for folder in (BASE, DATA, OUTPUT, HISTORY, LOGS):
    folder.mkdir(parents=True, exist_ok=True)
