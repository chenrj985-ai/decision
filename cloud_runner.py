# -*- coding: utf-8 -*-
"""V6 云端总控：风险更新 -> 决策生成 -> 健康检查 -> Pages 站点准备。
任何外部新闻源失败都不会阻断主决策；主决策或页面缺失则明确失败。
"""
from __future__ import annotations
import json, os, shutil, subprocess, sys, traceback
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT = BASE / 'output'; DATA = BASE / 'data'; SITE = BASE / 'site'; LOGS = BASE / 'logs'
for d in (OUT, DATA, SITE, LOGS): d.mkdir(parents=True, exist_ok=True)

def run_step(name, script, required):
    print(f'\n===== {name} =====', flush=True)
    cp = subprocess.run([sys.executable, str(BASE/script)], cwd=BASE, text=True)
    if cp.returncode != 0:
        msg=f'{name} failed with code {cp.returncode}'
        if required: raise RuntimeError(msg)
        print('[WARN] '+msg+'; continue with cached/price data.', flush=True)
    return cp.returncode

def copy_if(src, dst):
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src,dst); return True
    return False

def prepare_site():
    if SITE.exists(): shutil.rmtree(SITE)
    (SITE/'files').mkdir(parents=True); (SITE/'history').mkdir(parents=True)
    main=OUT/'mobile_latest.html'
    if not main.exists() or main.stat().st_size < 1000:
        raise RuntimeError('output/mobile_latest.html missing or too small')
    shutil.copy2(main,SITE/'index.html'); shutil.copy2(main,SITE/'mobile_latest.html')
    files=['latest_decision.txt','buy_candidates.csv','position_decisions.csv','etf_rotation.csv','all_scores.csv']
    for f in files: copy_if(OUT/f,SITE/'files'/f)
    for f in (OUT/'history').glob('*.html'): shutil.copy2(f,SITE/'history'/f.name)
    (SITE/'.nojekyll').write_text('',encoding='utf-8')
    (SITE/'last_update_utc.txt').write_text(datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),encoding='utf-8')
    # machine-readable status for mobile/cache busting
    status={
      'version':'6.0','generated_utc':datetime.now(timezone.utc).isoformat(),
      'page':'index.html','files':[f for f in files if (OUT/f).exists()]
    }
    (SITE/'status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')

def health():
    required=[OUT/'mobile_latest.html',OUT/'all_scores.csv',OUT/'etf_rotation.csv']
    missing=[str(x.relative_to(BASE)) for x in required if not x.exists() or x.stat().st_size==0]
    report={'ok':not missing,'missing':missing,'checked_at':datetime.now().isoformat(),'version':'6.0'}
    (OUT/'health.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if missing: raise RuntimeError('health check failed: '+', '.join(missing))

if __name__=='__main__':
    try:
        run_step('1/2 Update global risk, news and announcements','update_risk_data.py',False)
        run_step('2/2 Generate decisions','main.py',True)
        health(); prepare_site()
        print('\n[OK] V6 cloud build completed.',flush=True)
    except Exception:
        traceback.print_exc(); sys.exit(1)
