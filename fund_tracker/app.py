# -*- coding: utf-8 -*-
"""基金限购额度盯盘 · Flask 应用

启动：  python app.py
访问：  http://127.0.0.1:5088
"""
import io
import csv
import json
import os
import threading
import time
from datetime import date, datetime

from flask import Flask, Response, jsonify, render_template, request

import db
import fetcher

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE, "config.json")

DEFAULT_CONFIG = {
    "port": 5088,
    "fetch_times": ["09:30", "21:30"],
    "enable_scheduler": True,
    "workers": 5,
}

app = Flask(__name__,
            template_folder=os.path.join(BASE, "templates"),
            static_folder=os.path.join(BASE, "static"))
app.config["JSON_AS_ASCII"] = False

_fetch_lock = threading.Lock()
_fetch_state = {"running": False, "message": "", "started_at": None, "finished_at": None}
_done_marks = set()


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:  # noqa: BLE001
        pass
    return cfg


# --------------------------------------------------------------------------- 抓取任务

def do_fetch(note="手动"):
    """执行一次抓取并落库；返回统计字典。同一时间只允许一个任务。"""
    if not _fetch_lock.acquire(blocking=False):
        return {"skipped": True, "message": "已有抓取任务正在运行"}
    _fetch_state.update(running=True, message="抓取中…",
                        started_at=datetime.now().strftime("%H:%M:%S"))
    try:
        db.init_db()
        funds = fetcher.load_funds()
        cfg = load_config()
        results = fetcher.fetch_all(funds, workers=int(cfg.get("workers", 8)))
        stat = db.save_results(results)
        fails = [r["code"] for r in results if not r.get("ok")]
        stat["fail_codes"] = fails
        stat["note"] = note
        _fetch_state["message"] = f"完成：成功 {stat['ok']} 只，失败 {len(fails)} 只"
        return stat
    except Exception as e:  # noqa: BLE001
        _fetch_state["message"] = f"抓取失败：{e}"
        return {"error": str(e)}
    finally:
        _fetch_state["running"] = False
        _fetch_state["finished_at"] = datetime.now().strftime("%H:%M:%S")
        _fetch_lock.release()


def scheduler_loop():
    """内置定时器：到点自动抓取（默认 09:30 / 21:30）"""
    while True:
        try:
            cfg = load_config()
            if cfg.get("enable_scheduler", True):
                now = datetime.now()
                hm = now.strftime("%H:%M")
                today = date.today().isoformat()
                if hm in [str(t) for t in cfg.get("fetch_times", [])]:
                    mark = f"{today} {hm}"
                    if mark not in _done_marks:
                        _done_marks.add(mark)
                        threading.Thread(target=do_fetch, args=(f"定时 {hm}",),
                                         daemon=True).start()
        except Exception:  # noqa: BLE001
            pass
        time.sleep(25)


# --------------------------------------------------------------------------- 页面

@app.route("/")
def index():
    return render_template("index.html")


# --------------------------------------------------------------------------- API

def _fmt_limit(amount):
    if amount is None:
        return ""
    if amount >= 10000:
        v = amount / 10000.0
        return ("%g" % v) + "万元"
    return ("%g" % amount) + "元"


def _eff(row):
    """有效额度：暂停申购时不存在「限额」，返回 None"""
    return fetcher.effective_limit(row.get("trade_status"), row.get("limit_amount"))


def _eff_disp(row):
    """额度展示文案：可买 -> 具体额度；暂停申购 -> 暂停申购"""
    st = row.get("trade_status") or ""
    if fetcher.is_buyable(st):
        return _fmt_limit(row.get("limit_amount")) or "—"
    return "暂停申购" if "暂停" in st else "—"


def _decorate(row):
    """给一条记录补上展示字段"""
    st = row.get("trade_status") or ""
    eff = _eff(row)
    short = _fmt_limit(eff) or "—"
    return {
        "status_label": fetcher.status_label(st),
        "buyable": fetcher.is_buyable(st),
        # 表格里的额度列：暂停申购没有限额一说，显示 —
        "limit_display": short,
        # 变化描述里用长文案，「100元 → 暂停申购」比「100元 → —」清楚
        "limit_long": short if eff is not None else ("暂停申购" if "暂停" in st else "—"),
        "limit_amount": eff,          # 前端按有效额度比较大小
        "raw_limit_amount": row.get("limit_amount"),
        "raw_limit_text": row.get("limit_text") or "",
    }


@app.route("/api/snapshot")
def api_snapshot():
    rows = db.latest_snapshot()
    funds = fetcher.load_funds()
    cat_map = {f["code"]: f["category"] for f in funds}
    order = {f["code"]: i for i, f in enumerate(funds)}
    rows.sort(key=lambda r: (order.get(r["code"], 999), r["code"]))

    out = []
    for r in rows:
        code = r["code"]
        # 找到上一条记录，用于展示额度变化
        with db.connect() as conn:
            prev = conn.execute(
                "SELECT * FROM daily_record WHERE code=? AND snap_date<? "
                "ORDER BY snap_date DESC LIMIT 1", (code, r["snap_date"])).fetchone()
        prev = dict(prev) if prev else None

        changed = False
        change_desc = ""
        amount_changed = False
        curr = _decorate(r)
        prev_dec = _decorate(prev) if prev else None
        if prev_dec:
            if curr["limit_amount"] != prev_dec["limit_amount"]:
                changed = amount_changed = True
                change_desc = f'{prev_dec["limit_long"]} → {curr["limit_long"]}'
            elif curr["status_label"] != prev_dec["status_label"]:
                changed = True
                change_desc = (f'{prev_dec["status_label"] or "—"} → '
                               f'{curr["status_label"] or "—"}')

        out.append({
            "code": code,
            "name": r.get("fund_name") or "",
            # 分类以 funds.txt 为准（改了清单立即生效）；基金已从清单移除时回落到库里的旧值
            "category": cat_map.get(code) or r.get("category") or fetcher.DEFAULT_CATEGORY,
            "snap_date": r.get("snap_date"),
            "trade_status": r.get("trade_status") or "",
            "status_label": curr["status_label"],
            "buyable": curr["buyable"],
            "limit_text": curr["raw_limit_text"],
            "limit_amount": curr["limit_amount"],
            "raw_limit_amount": curr["raw_limit_amount"],
            "limit_display": curr["limit_display"],
            "prev_limit_amount": prev_dec["limit_amount"] if prev_dec else None,
            "prev_limit_display": prev_dec["limit_display"] if prev_dec else None,
            "prev_snap_date": prev.get("snap_date") if prev else None,
            "redeem_status": r.get("redeem_status") or "",
            "nav": r.get("nav"),
            "nav_date": r.get("nav_date"),
            "day_growth": r.get("day_growth"),
            "scale_yi": r.get("scale_yi"),
            "scale_date": r.get("scale_date"),
            "changed": changed,
            "amount_changed": amount_changed,
            "change_desc": change_desc,
            "missing": code not in cat_map,
        })

    # 分类清单（按 CATEGORY_ORDER 排序，附带当前只数）——前端据此生成切换按钮
    counts = {}
    for it in out:
        counts[it["category"]] = counts.get(it["category"], 0) + 1
    cats = sorted(counts.keys(), key=lambda c: (fetcher.category_rank(c), c))
    categories = [{"name": c, "count": counts[c]} for c in cats]
    if cats:
        categories.insert(0, {"name": "全部", "count": len(out)})

    last = db.last_fetch()
    days = db.record_days()
    return jsonify({
        "items": out,
        "categories": categories,
        "last_fetch": last,
        "record_days": days,
        "today": date.today().isoformat(),
        "state": _fetch_state,
    })


@app.route("/api/changes")
def api_changes():
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT d.code, d.snap_date, d.fund_name, d.category, d.trade_status, d.limit_text,
                   d.limit_amount,
                   (SELECT p.limit_amount FROM daily_record p
                     WHERE p.code=d.code AND p.snap_date<d.snap_date
                     ORDER BY p.snap_date DESC LIMIT 1) AS prev_amount,
                   (SELECT p.limit_text FROM daily_record p
                     WHERE p.code=d.code AND p.snap_date<d.snap_date
                     ORDER BY p.snap_date DESC LIMIT 1) AS prev_text,
                   (SELECT p.trade_status FROM daily_record p
                     WHERE p.code=d.code AND p.snap_date<d.snap_date
                     ORDER BY p.snap_date DESC LIMIT 1) AS prev_status,
                   (SELECT MAX(p.snap_date) FROM daily_record p
                     WHERE p.code=d.code AND p.snap_date<d.snap_date) AS prev_date
            FROM daily_record d
            JOIN (SELECT code, MAX(snap_date) mx FROM daily_record GROUP BY code) m
              ON d.code=m.code AND d.snap_date=m.mx
            ORDER BY d.code
            """
        ).fetchall()

    items = []
    cmap = fetcher.category_map()
    for r in rows:
        r = dict(r)
        if r["prev_date"] is None:
            continue
        cur = _decorate(r)
        prev = _decorate({"trade_status": r["prev_status"],
                          "limit_amount": r["prev_amount"],
                          "limit_text": r["prev_text"]})
        amt_changed = cur["limit_amount"] != prev["limit_amount"]
        st_changed = cur["status_label"] != prev["status_label"]
        if not (amt_changed or st_changed):
            continue
        # 变化方向：变大 -> up（蓝），变小 -> down（黄）
        direction = None
        if amt_changed:
            ca = cur["limit_amount"] if cur["limit_amount"] is not None else 0
            pa = prev["limit_amount"] if prev["limit_amount"] is not None else 0
            direction = "up" if ca > pa else "down"
        items.append({
            "code": r["code"],
            "name": r["fund_name"] or "",
            "category": cmap.get(r["code"]) or r.get("category") or fetcher.DEFAULT_CATEGORY,
            "snap_date": r["snap_date"],
            "prev_date": r["prev_date"],
            "from_limit": prev["limit_long"],
            "to_limit": cur["limit_long"],
            "from_status": prev["status_label"],
            "to_status": cur["status_label"],
            "amount_changed": amt_changed,
            "status_changed": st_changed,
            "direction": direction,
        })
    return jsonify({"items": items})


@app.route("/api/history")
def api_history():
    code = request.args.get("code") or None
    days = int(request.args.get("days") or 365)
    rows = db.history(code=code, days=days)
    cmap = fetcher.category_map()
    for r in rows:
        r["category"] = cmap.get(r.get("code")) or r.get("category") or fetcher.DEFAULT_CATEGORY
        r.update(_decorate(r))
    return jsonify({"items": rows})


@app.route("/api/trend")
def api_trend():
    code = request.args.get("code", "")
    if not code:
        return jsonify({"items": []})
    items = db.trend(code)
    for r in items:
        st = r.get("trade_status") or ""
        r["status_label"] = fetcher.status_label(st)
        r["buyable"] = fetcher.is_buyable(st)
        r["eff_limit"] = fetcher.effective_limit(st, r.get("limit_amount"))
    return jsonify({"items": items})


@app.route("/api/funds")
def api_funds():
    funds = fetcher.load_funds()
    with db.connect() as conn:
        rows = conn.execute("SELECT code, name FROM funds").fetchall()
    names = {r["code"]: r["name"] for r in rows}
    return jsonify({"items": [{"code": f["code"], "name": names.get(f["code"], ""),
                               "category": f["category"]} for f in funds]})


@app.route("/api/fetch", methods=["POST"])
def api_fetch():
    if _fetch_state["running"]:
        return jsonify({"ok": False, "message": "抓取正在进行中，请稍候"}), 409
    threading.Thread(target=do_fetch, args=("手动",), daemon=True).start()
    return jsonify({"ok": True, "message": "已开始抓取，约 30~90 秒后刷新查看"})


@app.route("/api/fetch_status")
def api_fetch_status():
    return jsonify(_fetch_state)


@app.route("/api/export")
def api_export():
    code = request.args.get("code") or None
    days = int(request.args.get("days") or 0)
    rows = db.history(code=code, days=days)
    cmap = fetcher.category_map()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["记录日期", "基金代码", "基金名称", "分类", "申购状态", "单日限购额度", "额度(元)",
                "赎回状态", "单位净值", "净值日期", "日涨幅%", "规模(亿元)", "规模截止日"])
    for r in rows:
        st = r.get("trade_status") or ""
        w.writerow([r.get("snap_date"), r.get("code"), r.get("fund_name"),
                    cmap.get(r.get("code")) or r.get("category"),
                    fetcher.status_label(st),
                    fetcher.effective_limit(st, r.get("limit_amount")),
                    fetcher.effective_limit(st, r.get("limit_amount")),
                    r.get("redeem_status"), r.get("nav"), r.get("nav_date"),
                    r.get("day_growth"), r.get("scale_yi"), r.get("scale_date")])
    data = "\ufeff" + buf.getvalue()  # BOM，Excel 直接打开不乱码
    fname = f"fund_limit_{code or 'ALL'}_{date.today().isoformat()}.csv"
    return Response(data, mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# --------------------------------------------------------------------------- 入口

def main():
    db.init_db()
    cfg = load_config()
    port = int(cfg.get("port", 5088))
    if cfg.get("enable_scheduler", True):
        threading.Thread(target=scheduler_loop, daemon=True).start()
    print("=" * 60)
    print("  基金限购额度盯盘已启动")
    print(f"  访问地址：http://127.0.0.1:{port}")
    print(f"  基金只数：{len(fetcher.load_funds())} 只")
    print(f"  定时抓取：{', '.join(cfg.get('fetch_times', [])) or '已关闭'}")
    print("=" * 60)
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
