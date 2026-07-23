from pathlib import Path
import pandas as pd

base = Path(__file__).resolve().parent
file = base / "data" / "recommendation_history.csv"

if not file.exists():
    print("未发现 recommendation_history.csv，无需修复。")
else:
    try:
        df = pd.read_csv(file, encoding="utf-8-sig", dtype=str)
    except UnicodeDecodeError:
        df = pd.read_csv(file, encoding="gbk", dtype=str)

    numeric_columns = [
        "price", "score", "last_price",
        "max_return", "min_return", "days"
    ]
    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    if "code" in df.columns:
        df["code"] = (
            df["code"].astype(str)
            .str.extract(r"(\d+)")[0]
            .str.zfill(6)
        )

    df.to_csv(file, index=False, encoding="utf-8-sig")
    print("推荐历史文件已修复：", file)

input("按回车键退出...")
