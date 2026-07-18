from __future__ import annotations

import json
from pathlib import Path

from .utils import ROOT, atomic_write, now_cn

CSS = """
body{font-family:Arial,'Microsoft YaHei',sans-serif;background:#f3f5f8;margin:0;color:#1f2937}.wrap{max-width:1100px;margin:auto;padding:18px}.hero{background:#111827;color:white;padding:22px;border-radius:16px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px;margin-top:14px}.card{background:white;padding:16px;border-radius:14px;box-shadow:0 2px 12px #0001}.score{font-size:30px;font-weight:700}.tag{display:inline-block;padding:4px 9px;border-radius:999px;background:#eef2ff;margin:2px}.good{color:#047857}.bad{color:#b91c1c}table{width:100%;border-collapse:collapse}th,td{padding:9px;border-bottom:1px solid #e5e7eb;text-align:left;font-size:14px}a{color:#2563eb;text-decoration:none}.muted{color:#6b7280;font-size:13px}@media(max-width:650px){th:nth-child(4),td:nth-child(4){display:none}.wrap{padding:8px}}
"""


def _fmt(v, n=2):
    return "—" if v is None else f"{v:.{n}f}"


def build_site(snapshot: dict) -> None:
    risk = snapshot["risk"]
    rows = []
    for s in snapshot["stocks"]:
        rows.append(f"<tr><td>{s['code']}</td><td>{s['name']}</td><td><b>{s['decision']['score']}</b></td><td>{_fmt(s['quote'].get('change_pct'))}%</td><td>{s['decision']['action']}</td></tr>")
    etfs = "".join(f"<tr><td>{k}</td><td>{_fmt(v.get('change_pct'))}%</td><td>{_fmt(v.get('ma20_gap_pct'))}%</td></tr>" for k,v in snapshot["etfs"].items())
    news = "".join(f"<li><span class='tag'>{x['tag']}</span> <a href='{x['link']}'>{x['title']}</a></li>" for x in snapshot["news"].get("items", [])[:8]) or "<li>新闻源暂不可用，系统已使用缓存或降级运行。</li>"
    html = f"""<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>V6 股票决策</title><style>{CSS}</style></head><body><div class='wrap'><div class='hero'><h1>Stock Decision System V6</h1><div>北京时间：{snapshot['generated_at']}</div><div class='score'>风险 {risk['score']} · {risk['level']} · {risk['regime']}</div><div class='muted'>{'；'.join(risk.get('reasons',[])) or '未发现显著全球风险信号'}</div></div><div class='grid'><div class='card'><h2>推荐排序</h2><table><thead><tr><th>代码</th><th>名称</th><th>评分</th><th>涨跌</th><th>动作</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div><div class='card'><h2>ETF轮动</h2><table><tr><th>方向</th><th>涨跌</th><th>20日偏离</th></tr>{etfs}</table></div></div><div class='card' style='margin-top:14px'><h2>国际新闻风险</h2><ul>{news}</ul><div class='muted'>新闻来源：{snapshot['news'].get('source')}</div></div><div class='card' style='margin-top:14px'><h2>运行状态</h2><div>成功抓取个股：{snapshot['health']['stocks_ok']}/{snapshot['health']['stocks_total']}</div><div>成功抓取ETF：{snapshot['health']['etfs_ok']}/{snapshot['health']['etfs_total']}</div><p class='muted'>本页面仅作量化辅助，不构成投资建议。</p></div></div></body></html>"""
    atomic_write(ROOT / "site/index.html", html)
    atomic_write(ROOT / "site/latest.json", json.dumps(snapshot, ensure_ascii=False, indent=2))
