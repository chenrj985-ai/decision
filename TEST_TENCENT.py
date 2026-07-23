from app.providers import fetch_tencent
from app.utils import load_config, disable_environment_proxy

disable_environment_proxy()
config = load_config()
symbols = [
    "sh000001", "sz399006", "sh510300",
    "sh512760", "sh600536", "sz300394"
]
quotes = fetch_tencent(symbols, config)

print("=" * 70)
print("腾讯行情测试")
print("=" * 70)
for sym in symbols:
    q = quotes.get(sym)
    if q:
        print(
            f"{sym:10s} {q.name:10s} "
            f"现价 {q.price:10.3f} 涨跌 {q.pct:+7.2f}% "
            f"时间 {q.quote_time}"
        )
    else:
        print(f"{sym:10s} 未取得")
print("=" * 70)
