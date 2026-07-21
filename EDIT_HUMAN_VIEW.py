from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

BASE = Path(__file__).resolve().parent
FILE = BASE / "config" / "human_view.json"
SECTORS = ["PCB","半导体","光模块","AI算力","软件","机器人","创新药","军工","新能源","高股息"]


def load():
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


data = load()
root = tk.Tk()
root.title("V7 Pro 人工盘面设置")
root.geometry("700x720")
root.resizable(False, False)

frm = ttk.Frame(root, padding=16)
frm.pack(fill="both", expand=True)

ttk.Label(frm, text="人工盘面设置", font=("Microsoft YaHei UI", 18, "bold")).pack(anchor="w")
ttk.Label(
    frm,
    text="人工判断只调整排序，不会绕过重大利空、爆雷指数和行业禁买等硬过滤。",
    foreground="#555"
).pack(anchor="w", pady=(2, 12))

flags = {}
line = ttk.Frame(frm)
line.pack(fill="x", pady=4)
for key, label in [
    ("allow_chase", "允许追高"),
    ("allow_oversold", "允许超跌试仓"),
    ("prefer_pullback", "优先回踩买")
]:
    v = tk.BooleanVar(value=bool(data.get(key, False)))
    flags[key] = v
    ttk.Checkbutton(line, text=label, variable=v).pack(side="left", padx=(0, 18))

ttk.Label(frm, text="板块人工加减分（-25 到 +25）").pack(anchor="w", pady=(12, 6))
entries = {}
grid = ttk.Frame(frm)
grid.pack(fill="x")
for i, sec in enumerate(SECTORS):
    ttk.Label(grid, text=sec, width=10).grid(row=i//2, column=(i%2)*2, padx=5, pady=5, sticky="w")
    ent = ttk.Entry(grid, width=10)
    ent.insert(0, str(data.get("sector_adjustments", {}).get(sec, 0)))
    ent.grid(row=i//2, column=(i%2)*2+1, padx=5, pady=5)
    entries[sec] = ent

ttk.Label(frm, text="重点板块（逗号分隔）").pack(anchor="w", pady=(14, 3))
focus = ttk.Entry(frm)
focus.insert(0, ",".join(data.get("focus_sectors", [])))
focus.pack(fill="x")

ttk.Label(frm, text="回避板块（逗号分隔）").pack(anchor="w", pady=(10, 3))
avoid = ttk.Entry(frm)
avoid.insert(0, ",".join(data.get("avoid_sectors", [])))
avoid.pack(fill="x")

ttk.Label(frm, text="个股人工调整（每行：股票代码,分数，例如 688347,8）").pack(anchor="w", pady=(10, 3))
stocks = tk.Text(frm, height=6)
for code, score in data.get("stock_adjustments", {}).items():
    stocks.insert("end", f"{code},{score}\n")
stocks.pack(fill="x")

ttk.Label(frm, text="今日盘面备注").pack(anchor="w", pady=(10, 3))
note = tk.Text(frm, height=4)
note.insert("1.0", data.get("market_note", ""))
note.pack(fill="x")


def parse_list(s):
    return [x.strip() for x in s.replace("，", ",").split(",") if x.strip()]


def save():
    try:
        sector_adjustments = {}
        for sec, ent in entries.items():
            val = float(ent.get().strip() or 0)
            sector_adjustments[sec] = max(-25, min(25, val))

        stock_adjustments = {}
        for line in stocks.get("1.0", "end").splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.replace("，", ",").split(",")
            if len(parts) != 2:
                raise ValueError(f"个股调整格式错误：{line}")
            stock_adjustments[parts[0].strip()] = max(-25, min(25, float(parts[1])))

        current = load()
        current.update({
            "enabled": True,
            "manual_weight": 0.18,
            "focus_sectors": parse_list(focus.get()),
            "avoid_sectors": parse_list(avoid.get()),
            "sector_adjustments": sector_adjustments,
            "stock_adjustments": stock_adjustments,
            "allow_chase": flags["allow_chase"].get(),
            "allow_oversold": flags["allow_oversold"].get(),
            "prefer_pullback": flags["prefer_pullback"].get(),
            "market_note": note.get("1.0", "end").strip()
        })
        FILE.parent.mkdir(exist_ok=True)
        FILE.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        messagebox.showinfo("保存成功", "人工盘面设置已保存。\n重新运行 RUN_V7_PRO.cmd 即可生效。")
    except Exception as exc:
        messagebox.showerror("保存失败", str(exc))


ttk.Button(frm, text="保存人工设置", command=save).pack(pady=16)
root.mainloop()
