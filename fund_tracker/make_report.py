# -*- coding: utf-8 -*-
"""生成当日静态归档报告 report/YYYY-MM-DD.html

页面应用（app.py）是主入口；本脚本额外产出一份不依赖服务端的单文件归档，
方便离线查看 / 留存历史。用法：
    python make_report.py
"""
import os
import re
from datetime import date, datetime

import db
import fetcher

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE, "report")

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.html$")


def fmt_amount(v):
    if v is None:
        return "—"
    n = float(v)
    if n >= 10000:
        return f"{n / 10000:g}万元"
    return f"{n:g}元"


def esc(s):
    return (str(s if s is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def status_class(s):
    """暂停申购 -> 红；能买 -> 绿"""
    if not s:
        return "tag-other"
    return "tag-suspend" if not fetcher.is_buyable(s) else "tag-buy"


def trend_svg(rows):
    """静态阶梯图：额度走势。暂停申购当天没有额度，点画在坐标轴底端并标注「暂停」"""
    import math
    pts = list(rows)
    if len(pts) < 2:
        return ""
    eff = [fetcher.effective_limit(r.get("trade_status"), r.get("limit_amount")) for r in pts]
    buy = [float(v) for v in eff if v is not None]
    if not buy:
        return ""

    W, H, padL, padR, padT, padB = 1000, 220, 82, 34, 34, 42
    iw, ih = W - padL - padR, H - padT - padB
    mx, mn = max(buy), min(buy)
    use_log = mn > 0 and mx / mn >= 8
    y_lo = math.log10(max(mn * 0.6, 0.5)) if use_log else 0.0
    y_hi = math.log10(mx * 1.4) if use_log else mx * 1.2
    base = padT + ih

    def to_y(v):
        t = (math.log10(max(v, 0.5)) - y_lo) / (y_hi - y_lo) if use_log else (v - y_lo) / (y_hi - y_lo)
        return base - t * ih

    n = len(pts)
    to_x = lambda i: padL + (i * iw) / (n - 1)  # noqa: E731
    y_of = lambda i: base if eff[i] is None else to_y(float(eff[i]))  # noqa: E731

    s = ""
    for k in range(5):
        v = 10 ** (y_lo + (k / 4) * (y_hi - y_lo)) if use_log else y_lo + (k / 4) * (y_hi - y_lo)
        y = to_y(v)
        label = "0元" if (k == 0 and not use_log) else fmt_amount(v)
        s += (f'<line x1="{padL}" y1="{y:.1f}" x2="{W - padR}" y2="{y:.1f}" '
              f'stroke="#eef1f6" stroke-width="1"/>'
              f'<text x="{padL - 10}" y="{y + 4:.1f}" text-anchor="end" font-size="11" '
              f'fill="#8b93a1">{label}</text>')

    d = ""
    for i in range(n):
        x = to_x(i)
        if i == 0:
            d += f"M {x:.1f} {y_of(0):.1f}"
        else:
            d += f" L {x:.1f} {y_of(i - 1):.1f} L {x:.1f} {y_of(i):.1f}"
    s += f'<path d="{d}" fill="none" stroke="#2563eb" stroke-width="2"/>'

    step = max(1, (n + 13) // 14)
    for i, p in enumerate(pts):
        x, y = to_x(i), y_of(i)
        ok = eff[i] is not None
        color = "#16a34a" if ok else "#dc2626"
        s += (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#fff" stroke="{color}" '
              f'stroke-width="2"/>')
        if i % step == 0 or i == n - 1:
            label = fmt_amount(eff[i]) if ok else "暂停"
            fill = "#1f2937" if ok else "#dc2626"
            s += (f'<text x="{x:.1f}" y="{y - 11:.1f}" text-anchor="middle" font-size="11" '
                  f'font-weight="700" fill="{fill}">{label}</text>'
                  f'<text x="{x:.1f}" y="{H - padB + 18}" text-anchor="middle" font-size="10" '
                  f'fill="#8b93a1">{esc((p.get("snap_date") or "")[5:])}</text>')
    return f'<svg viewBox="0 0 {W} {H}" style="width:100%;height:auto;display:block">{s}</svg>'


CSS = """
body{margin:0;background:#f4f6fa;color:#1f2937;font:14px/1.6 "Microsoft YaHei","PingFang SC",system-ui,sans-serif}
.wrap{max-width:1400px;margin:0 auto;padding:0 20px 40px}
.top{background:linear-gradient(90deg,#1e3a8a,#2563eb);color:#fff;padding:20px 0;margin-bottom:18px}
.top h1{margin:0;font-size:21px}.top p{margin:4px 0 0;font-size:13px;color:#cddcff}
.panel{background:#fff;border:1px solid #e4e8f0;border-radius:10px;margin-bottom:16px;overflow:hidden}
.panel h2{margin:0;padding:13px 18px;font-size:15px;border-bottom:1px solid #eef1f6}
.panel h2::before{content:"";display:inline-block;width:4px;height:14px;background:#2563eb;border-radius:2px;margin-right:9px;vertical-align:-2px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#f8fafc;color:#5b6472;text-align:left;padding:9px 12px;border-bottom:1px solid #e4e8f0;white-space:nowrap}
td{padding:9px 12px;border-bottom:1px solid #eef1f6}
tr:nth-child(even) td{background:#fcfdff}
.num{text-align:right;font-variant-numeric:tabular-nums}
.code{font-family:Consolas,monospace;color:#5b6472}
.tag{display:inline-block;padding:2px 8px;border-radius:5px;font-size:12px;border:1px solid transparent}
.tag-suspend{background:#fef2f2;color:#b91c1c;border-color:#fecaca}
.tag-buy{background:#ecfdf5;color:#047857;border-color:#a7f3d0}
.tag-limited{background:#ecfdf5;color:#047857;border-color:#a7f3d0}
.tag-open{background:#ecfdf5;color:#047857;border-color:#a7f3d0}
.tag-other{background:#f1f5f9;color:#475569;border-color:#e2e8f0}
.up{color:#d93025;font-weight:600}.down{color:#12a150;font-weight:600}
.cat{display:inline-block;padding:2px 8px;border-radius:5px;font-size:12px;background:#f1f5f9;color:#475569;border:1px solid #e2e8f0;white-space:nowrap}
.cat-0{background:#eff6ff;color:#1d4ed8;border-color:#bfdbfe}
.cat-1{background:#ecfdf5;color:#047857;border-color:#a7f3d0}
.cat-2{background:#faf5ff;color:#7e22ce;border-color:#e9d5ff}
.cat-3{background:#fff7ed;color:#b45309;border-color:#fed7aa}
.catbar{display:flex;gap:6px;flex-wrap:wrap;padding:10px 18px 0}
.catbar button{font-family:inherit;font-size:12.5px;line-height:1;padding:6px 13px;border-radius:999px;
  border:1px solid #e4e8f0;background:#fff;color:#5b6472;cursor:pointer;white-space:nowrap}
.catbar button:hover{background:#f7f9fc;color:#1f2937}
.catbar button.on{background:#2563eb;border-color:#2563eb;color:#fff;font-weight:600}
.catbar button .n{opacity:.7;margin-left:4px}
.chg{padding:10px 18px;border-bottom:1px solid #eef1f6;background:#f8fafc;font-size:13px}
.chg b{color:#334155}
.chg.up-chg{background:#eff6ff;border-color:#bfdbfe}.chg.up-chg b{color:#2563eb}
.chg.down-chg{background:#fefce8;border-color:#fde68a}.chg.down-chg b{color:#a16207}
.empty{padding:20px;color:#8b93a1;text-align:center}
.foot{text-align:center;color:#8b93a1;font-size:12px;padding:8px 0 0}
"""

# 静态归档里的分类切换（纯前端显隐，不依赖服务端）
FILTER_JS = """
(function () {
  var bar = document.querySelector('.catbar');
  if (!bar) return;
  var rows = Array.prototype.slice.call(document.querySelectorAll('#tbl tbody tr[data-cat]'));
  bar.addEventListener('click', function (e) {
    var b = e.target.closest('button[data-cat]');
    if (!b) return;
    var cat = b.getAttribute('data-cat');
    Array.prototype.forEach.call(bar.querySelectorAll('button'), function (x) {
      x.classList.toggle('on', x === b);
    });
    rows.forEach(function (tr) {
      tr.style.display = (cat === '全部' || tr.getAttribute('data-cat') === cat) ? '' : 'none';
    });
  });
})();
"""


INDEX_CSS = """
body{margin:0;background:#f4f6fa;color:#1f2937;font:14px/1.7 "Microsoft YaHei","PingFang SC",system-ui,sans-serif}
.top{background:linear-gradient(90deg,#1e3a8a,#2563eb);color:#fff;padding:20px 0;margin-bottom:18px}
.wrap{max-width:760px;margin:0 auto;padding:0 20px 40px}
.top h1{margin:0;font-size:21px}.top p{margin:4px 0 0;font-size:13px;color:#cddcff}
.panel{background:#fff;border:1px solid #e4e8f0;border-radius:10px;overflow:hidden}
.panel h2{margin:0;padding:13px 18px;font-size:15px;border-bottom:1px solid #eef1f6}
.panel h2::before{content:"";display:inline-block;width:4px;height:14px;background:#2563eb;border-radius:2px;margin-right:9px;vertical-align:-2px}
ul{list-style:none;margin:0;padding:6px 0}
li{border-bottom:1px solid #f2f5f9}
li:last-child{border-bottom:none}
li a{display:block;padding:11px 18px;color:#1d4ed8;text-decoration:none;font-size:14px}
li a:hover{background:#f7f9fc}
.badge{display:inline-block;margin-left:8px;padding:1px 8px;border-radius:999px;font-size:11px;
  background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe}
.n{float:right;color:#8b93a1;font-size:12px}
.foot{text-align:center;color:#8b93a1;font-size:12px;padding:14px 0 0}
"""


def build_index():
    """在 report/ 下生成 index.html —— 历史日报的目录页（GitHub Pages 的首页）"""
    if not os.path.isdir(OUT_DIR):
        return None
    files = sorted((f for f in os.listdir(OUT_DIR) if DATE_RE.match(f)), reverse=True)
    if not files:
        return None
    latest = files[0]
    items = []
    for f in files:
        badge = '<span class="badge">最新</span>' if f == latest else ""
        size = os.path.getsize(os.path.join(OUT_DIR, f)) / 1024
        items.append(f'<li><a href="{f}">{f[:-5]}{badge}'
                     f'<span class="n">{size:.0f} KB</span></a></li>')
    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>基金限购额度日报 · 归档</title><style>{INDEX_CSS}</style></head>
<body>
<div class="top"><div class="wrap"><h1>基金限购额度 · 日报归档</h1>
<p>共 {len(files)} 份 ｜ 最新：{latest[:-5]}</p></div></div>
<div class="wrap">
  <div class="panel"><h2>按日期查看</h2>
    <ul>{"".join(items)}</ul>
  </div>
  <div class="foot">数据来自公开网页，仅供个人记录参考，不构成投资建议。</div>
</div>
</body></html>"""
    path = os.path.join(OUT_DIR, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


def build():
    db.init_db()
    snap = db.latest_snapshot()
    days = db.record_days()
    today = date.today().isoformat()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 补分类 + 按分类归拢排序（同一分类的记录连在一起）
    # 分类以 funds.txt 为准，改了清单后历史记录也跟着变
    cmap = fetcher.category_map()
    for r in snap:
        r["category"] = cmap.get(r["code"]) or r.get("category") or fetcher.DEFAULT_CATEGORY
    snap.sort(key=lambda r: (fetcher.category_rank(r["category"]), r["category"], r["code"]))

    counts = {}
    for r in snap:
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    cat_names = sorted(counts, key=lambda c: (fetcher.category_rank(c), c))
    cat_bar = [("全部", len(snap))] + [(c, counts[c]) for c in cat_names]

    def dec(row):
        st = row.get("trade_status") or ""
        eff = fetcher.effective_limit(st, row.get("limit_amount"))
        short = fmt_amount(eff)
        return {
            "label": fetcher.status_label(st) or "—",
            "raw": st,
            "eff": eff,
            "short": short,
            # 表格里暂停申购没有限额一说，显示 —；变化描述里用「暂停申购」更清楚
            "long": short if eff is not None else ("暂停申购" if "暂停" in st else "—"),
        }

    rows_html = []
    for r in snap:
        d = dec(r)
        cat = r["category"]
        cat_cls = fetcher.category_rank(cat)
        cat_cls = f"cat-{cat_cls}" if cat_cls < len(fetcher.CATEGORY_ORDER) else "cat"
        growth = r.get("day_growth")
        if growth is None:
            g = "—"
        else:
            cls = "up" if growth > 0 else ("down" if growth < 0 else "")
            g = f'<span class="{cls}">{"+" if growth > 0 else ""}{growth:.2f}%</span>'
        rows_html.append(f"""<tr data-cat="{esc(cat)}">
          <td class="code">{esc(r["code"])}</td>
          <td>{esc(r.get("fund_name"))}</td>
          <td><span class="{cat_cls}">{esc(cat)}</span></td>
          <td><span class="tag {status_class(d["raw"])}">{esc(d["label"])}</span></td>
          <td class="num"><b>{d["short"]}</b></td>
          <td class="num">{f"{r['nav']:.4f}" if r.get("nav") else "—"}</td>
          <td class="num">{g}</td>
          <td class="num">{r.get("scale_yi") if r.get("scale_yi") is not None else "—"}</td>
          <td>{esc(r.get("nav_date") or "—")}</td>
        </tr>""")

    chg_html = []
    for r in snap:
        prev = db.previous_record(r["code"], r["snap_date"])
        if not prev:
            continue
        cur, old = dec(r), dec(prev)
        tail = f'（{esc(prev.get("snap_date"))} → {esc(r.get("snap_date"))}）'
        head = f'{esc(r["code"])} {esc(r.get("fund_name"))}'
        if cur["eff"] != old["eff"]:
            # 变大 -> 蓝，变小 -> 黄
            up = (cur["eff"] if cur["eff"] is not None else 0) > \
                 (old["eff"] if old["eff"] is not None else 0)
            chg_html.append(
                f'<div class="chg {"up-chg" if up else "down-chg"}">{head}：额度 '
                f'<b>{old["long"]} → {cur["long"]}</b>'
                f'<span style="color:#8b93a1">（{"变大" if up else "变小"}）</span>{tail}</div>')
        elif cur["label"] != old["label"]:
            chg_html.append(
                f'<div class="chg">{head}：状态 '
                f'<b>{esc(old["label"])} → {esc(cur["label"])}</b>{tail}</div>')

    tsvg = trend_svg(db.trend(snap[0]["code"])) if snap else ""

    bar_html = "".join(
        f'<button type="button" data-cat="{esc(n)}" class="{"on" if n == "全部" else ""}">'
        f'{esc(n)}<span class="n">{c}</span></button>'
        for n, c in cat_bar
    )
    cat_summary = " · ".join(f"{esc(n)} {c} 只" for n, c in cat_bar[1:])

    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>基金限购额度日报 {today}</title><style>{CSS}</style></head>
<body>
<div class="top"><div class="wrap"><h1>基金限购额度 · 每日记录（{today}）</h1>
<p>数据来源：天天基金网 ｜ 生成时间：{now} ｜ 共 {len(snap)} 只（{cat_summary}）｜ 已累计 {days.get("c") or 0} 个记录日（{days.get("mn") or "—"} ~ {days.get("mx") or "—"}）</p></div></div>
<div class="wrap">
  <div class="panel"><h2>额度总览</h2>
    <div class="catbar">{bar_html}</div>
    <table id="tbl"><thead><tr><th>代码</th><th>基金名称</th><th>分类</th><th>申购状态</th><th class="num">单日限购额度</th>
    <th class="num">单位净值</th><th class="num">日涨幅</th><th class="num">规模(亿)</th><th>净值日期</th></tr></thead>
    <tbody>{''.join(rows_html) or '<tr><td colspan="9" class="empty">暂无记录</td></tr>'}</tbody></table>
  </div>
  <div class="panel"><h2>额度 / 状态变动</h2>
    {''.join(chg_html) or '<div class="empty">最新记录与上一次相比无变化</div>'}
  </div>
  <div class="panel"><h2>额度走势（{esc(snap[0]["code"]) if snap else ""}）</h2>
    <div style="padding:10px 18px 0;font-size:12px;color:#8b93a1"><span style="color:#16a34a">绿色点＝当日可申购</span>；<span style="color:#dc2626">红色点（标注「暂停」）＝当日暂停申购，无额度</span>。</div>
    {tsvg or '<div class="empty">记录满 2 天后自动生成走势图</div>'}
  </div>
  <div class="foot">数据来自公开网页，仅供个人记录参考，不构成投资建议。额度以基金公司公告为准。</div>
</div>
<script>{FILTER_JS}</script>
</body></html>"""

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{today}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    latest = os.path.join(OUT_DIR, "latest.html")
    with open(latest, "w", encoding="utf-8") as f:
        f.write(html)
    return path


if __name__ == "__main__":
    p = build()
    print("已生成日报：", p)
    idx = build_index()
    if idx:
        print("已生成归档目录：", idx)
