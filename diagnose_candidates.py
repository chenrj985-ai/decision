from pathlib import Path
import pandas as pd

base = Path(__file__).resolve().parent
p = base / "output" / "all_scores.csv"
if not p.exists():
    raise SystemExit("尚未生成 output/all_scores.csv，请先运行程序。")

df = pd.read_csv(p, dtype={"code": str})
print("总股票数：", len(df))
print("\n候选等级：")
print(df.get("candidate_grade", pd.Series(dtype=str)).value_counts(dropna=False))
print("\n信号分布：")
print(df.get("signal", pd.Series(dtype=str)).value_counts(dropna=False).head(20))
cols = [c for c in [
    "code","name","candidate_grade","coach_score","signal",
    "event_risk_value","event_unknown","explosion_index","etf_grade",
    "pct","coach_action"
] if c in df.columns]
print("\n排名前15：")
print(df[cols].head(15).to_string(index=False))
