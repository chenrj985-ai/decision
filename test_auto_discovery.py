from app.utils import disable_environment_proxy, load_config
from app.providers import auto_discover

disable_environment_proxy()
cfg = load_config()
df = auto_discover(cfg)
print("\n自动发现数量：", len(df))
if df.empty:
    print("未发现候选，请查看 output/discovery_health.json")
else:
    print(df.head(20).to_string(index=False))
    print("\n详细状态：output/discovery_health.json")
