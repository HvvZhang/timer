# -*- coding: utf-8 -*-
"""把「本次抓取结果」整理成 Markdown 摘要，供 GitHub Actions 写进运行摘要页。

本地也能直接跑，用来快速看一眼当前库里的情况：
    python ci_summary.py

输出全部走 stdout（Markdown），不写任何文件。
"""
import sys
from collections import OrderedDict
from datetime import date

import db
import fetcher


def fmt(amount):
    if amount is None:
        return "—"
    n = float(amount)
    if n >= 10000:
        return f"{n / 10000:g}万元"
    return f"{n:g}元"


def dec(row):
    """一条记录的展示字段（与网页口径一致）"""
    st = (row or {}).get("trade_status") or ""
    eff = fetcher.effective_limit(st, (row or {}).get("limit_amount"))
    short = fmt(eff)
    return {
        "label": fetcher.status_label(st) or "—",
        "eff": eff,
        "short": short,
        "long": short if eff is not None else ("暂停申购" if "暂停" in st else "—"),
    }


def num(v, digits=2, suffix=""):
    if v is None:
        return "—"
    return f"{float(v):.{digits}f}{suffix}"


def main():
    db.init_db()
    snap = db.latest_snapshot()
    cmap = fetcher.category_map()
    last = db.last_fetch() or {}
    days = db.record_days() or {}

    for r in snap:
        r["category"] = cmap.get(r["code"]) or r.get("category") or fetcher.DEFAULT_CATEGORY
    snap.sort(key=lambda r: (fetcher.category_rank(r["category"]), r["category"], r["code"]))

    today = date.today().isoformat()
    ok = last.get("ok")
    failed = last.get("failed")

    print(f"## 基金限购额度 · {today}")
    print()

    if ok is None:
        print("> ⚠️ 本次没有找到抓取记录，`fetch_log` 为空——说明抓取阶段没跑到落库。")
    else:
        flags = []
        if failed:
            flags.append(f"⚠️ 失败 {failed} 只")
        flags.append(f"记录日 {today}")
        flags.append(f"累计 {days.get('c') or 0} 个记录日"
                     f"（{days.get('mn') or '—'} ~ {days.get('mx') or '—'}）")
        print(f"**抓取结果**：成功 **{ok}** 只 / 失败 {failed} 只 ｜ " + " ｜ ".join(flags))
    print()

    # ------------------------------------------------------------------ 变动
    print("### 额度 / 状态变动")
    changed = []
    for r in snap:
        prev = db.previous_record(r["code"], r["snap_date"])
        if not prev:
            continue
        cur, old = dec(r), dec(prev)
        if cur["eff"] == old["eff"] and cur["label"] == old["label"]:
            continue
        if cur["eff"] != old["eff"]:
            ca = cur["eff"] if cur["eff"] is not None else 0
            pa = old["eff"] if old["eff"] is not None else 0
            arrow = "🔵 变大" if ca > pa else "🟡 变小"
            changed.append(f"- {r['code']} {r.get('fund_name') or ''}："
                           f"**{old['long']} → {cur['long']}**（{arrow}）")
        else:
            changed.append(f"- {r['code']} {r.get('fund_name') or ''}："
                           f"状态 **{old['label']} → {cur['label']}**")
    if changed:
        print("\n".join(changed))
    else:
        print("今日额度无变动。")
    print()

    # ------------------------------------------------------------------ 分布
    buckets = OrderedDict()
    for r in snap:
        d = dec(r)
        key = d["short"] if d["eff"] is not None else f"无额度（{d['label']}）"
        buckets.setdefault(key, []).append(r["code"])
    print("### 额度分布")
    print()
    print("| 单日限购额度 | 只数 | 基金代码 |")
    print("|---|---|---|")
    for k, codes in buckets.items():
        print(f"| {k} | {len(codes)} | {'、'.join(codes)} |")
    print()

    # ------------------------------------------------------------------ 明细
    print("<details><summary>全部 %d 只明细（点开）</summary>" % len(snap))
    print()
    print("| 代码 | 基金名称 | 分类 | 申购状态 | 单日限购额度 | 单位净值 | 日涨幅 | 规模(亿) |")
    print("|---|---|---|---|---|---|---|---|")
    for r in snap:
        d = dec(r)
        g = r.get("day_growth")
        g = "—" if g is None else f"{'+' if g > 0 else ''}{g:.2f}%"
        print(f"| {r['code']} | {r.get('fund_name') or ''} | {r['category']} | {d['label']} | "
              f"{d['short']} | {num(r.get('nav'), 4)} | {g} | "
              f"{'—' if r.get('scale_yi') is None else r['scale_yi']} |")
    print()
    print("</details>")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001
        print(f"> ❌ 生成摘要失败：{type(e).__name__}: {e}")
        sys.exit(0)   # 摘要失败不应该让整个流程变红
