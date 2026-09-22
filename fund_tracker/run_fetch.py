# -*- coding: utf-8 -*-
"""单次抓取（供 Windows 计划任务 / 外部定时器调用）

用法：
    python run_fetch.py
抓取完成后直接把当日记录写入 data/funds.db，网页端打开即可看到。
"""
import sys
from datetime import datetime

import db
import fetcher


def main():
    db.init_db()
    codes = fetcher.load_codes()
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 开始抓取 {len(codes)} 只基金…")
    results = fetcher.fetch_all(codes)
    for r in results:
        flag = "OK " if r.get("ok") else "ERR"
        print(f"  {flag} {r['code']} {r.get('fund_name') or ''} "
              f"| {r.get('trade_status') or '-'} | 额度 {r.get('limit_text') or '-'} "
              f"| 净值 {r.get('nav') or '-'} | 规模 {r.get('scale_yi') or '-'}亿"
              f"{' | ' + r['error'] if r.get('error') else ''}")
    stat = db.save_results(results)
    print(f"[完成] 记录日期 {stat['date']}，成功 {stat['ok']} 只，失败 {stat['failed']} 只")
    return 0 if stat["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
