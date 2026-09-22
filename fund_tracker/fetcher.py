# -*- coding: utf-8 -*-
"""天天基金网抓取模块

数据来源（均为公开页面 / 公开接口）：
  1) 基金详情页  http://fund.eastmoney.com/{code}.html
     -> 交易状态、赎回状态、单日累计购买上限（限购额度）
  2) 基金走势数据 http://fund.eastmoney.com/pingzhongdata/{code}.js
     -> 基金全称、规模变动（季报，单位：亿元）
  3) 历史净值接口 https://api.fund.eastmoney.com/f10/lsjz
     -> 单位净值、净值日期、日涨幅、申购/赎回状态
"""
import os
import json
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

BASE = os.path.dirname(os.path.abspath(__file__))
FUNDS_FILE = os.path.join(BASE, "funds.txt")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

DEFAULT_CODES = [
    "006075", "050025", "017030", "017028", "007721", "007722", "161125",
    "012860", "017641", "019305", "096001", "008401", "018065", "018064",
]

# 分类（用于网页上的分组切换按钮）。顺序即按钮顺序，不在表里的分类排在后面。
CATEGORY_ORDER = ["标普", "纳指100", "纳指科技", "主动"]
DEFAULT_CATEGORY = "其他"

# funds.txt 每行：  代码,分类   # 备注
# 兼容旧格式（只有代码）、以及用空格 / 制表符 / 中文逗号分隔的写法
CODE_SPLIT_RE = re.compile(r"[,\s，、]+")
CODE_RE = re.compile(r"^\d{5,6}$")

TAG_RE = re.compile(r"<[^>]+>")
# 交易状态：</span><span class="staticCell">暂停申购 (<span>单日累计购买上限100.00元</span>)</span><span class="staticCell">开放赎回</span>
TRADE_RE = re.compile(
    r'交易状态[：:]\s*</span>\s*<span class="staticCell">(.*?)</span>\s*'
    r'<span class="staticCell">(.*?)</span>',
    re.S,
)
TRADE_FALLBACK_RE = re.compile(r'交易状态[：:]?(?:</span>)?((?:<span[^>]*>)?[^<]{1,80})')
LIMIT_RE = re.compile(r"上限\s*([0-9][0-9,\.]*)\s*(亿元|万元|元)")
UNIT = {"元": 1.0, "万元": 10000.0, "亿元": 100000000.0}


# --------------------------------------------------------------------------- 工具

def load_funds():
    """从 funds.txt 读取基金清单 -> [{'code': '006075', 'category': '标普'}]

    每行格式： 代码,分类   # 备注（# 后面的内容忽略）
    只有代码没有分类时归入「其他」；重复代码只保留第一次出现的。
    """
    if not os.path.exists(FUNDS_FILE):
        with open(FUNDS_FILE, "w", encoding="utf-8") as f:
            f.write("# 每行格式：代码,分类   # 备注。修改后下次抓取生效。\n")
            f.write("\n".join(f"{c},{DEFAULT_CATEGORY}" for c in DEFAULT_CODES) + "\n")
        return [{"code": c, "category": DEFAULT_CATEGORY} for c in DEFAULT_CODES]

    items, seen = [], set()
    with open(FUNDS_FILE, encoding="utf-8") as f:
        for raw in f:
            body = raw.split("#")[0].strip()
            if not body:
                continue
            parts = [p for p in CODE_SPLIT_RE.split(body) if p]
            code = parts[0]
            if not CODE_RE.match(code) or code in seen:
                continue
            seen.add(code)
            items.append({
                "code": code,
                "category": (parts[1] if len(parts) > 1 else "") or DEFAULT_CATEGORY,
            })
    if items:
        return items
    return [{"code": c, "category": DEFAULT_CATEGORY} for c in DEFAULT_CODES]


def load_codes():
    """只要代码列表（内部沿用 load_funds）"""
    return [f["code"] for f in load_funds()]


def category_map():
    """{代码: 分类}"""
    return {f["code"]: f["category"] for f in load_funds()}


def category_rank(cat):
    """分类排序权重：CATEGORY_ORDER 里的按顺序，其余排后面"""
    try:
        return CATEGORY_ORDER.index(cat)
    except ValueError:
        return len(CATEGORY_ORDER)


def _decode(resp):
    for enc in ("utf-8", "gbk", "gb18030"):
        try:
            return resp.content.decode(enc)
        except Exception:
            continue
    return resp.content.decode("utf-8", "ignore")


def _get(url, referer="http://fund.eastmoney.com/", timeout=15, retries=3):
    headers = {
        "User-Agent": UA,
        "Referer": referer,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    last = None
    for i in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 200 and r.content:
                return _decode(r)
            last = RuntimeError(f"HTTP {r.status_code}")
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(0.5 * (i + 1) + random.random() * 0.4)
    raise last if last else RuntimeError("unknown")


def _strip(s):
    return re.sub(r"\s+", " ", TAG_RE.sub("", s or "")).strip()


def parse_trade_status(html):
    """从详情页解析 (申购状态原文, 赎回状态原文)"""
    m = TRADE_RE.search(html)
    if m:
        return _strip(m.group(1)), _strip(m.group(2))
    m = TRADE_FALLBACK_RE.search(html)
    if m:
        return _strip(m.group(1)), ""
    return "", ""


def parse_limit(text):
    """从状态文本解析限购额度 -> (原文如 '100.00元', 归一化为元的数值)"""
    m = LIMIT_RE.search(text or "")
    if not m:
        return "", None
    num = float(m.group(1).replace(",", ""))
    unit = m.group(2)
    return f"{m.group(1)}{unit}", num * UNIT[unit]


# --------------------------------------------------------------------------- 状态判定
# 展示规则（全局统一，app.py / make_report.py / 前端都走这里）：
#   暂停申购          -> 状态只显示「暂停申购」四个字，红色；此时不存在「限额」概念，额度为 —
#   限大额 / 开放申购 -> 可购买，绿色；额度正常显示
#   额度变化：变小 -> 黄色；变大 -> 蓝色

PAREN_RE = re.compile(r"[（(][^）)]*[）)]")


def status_label(status):
    """「暂停申购 (单日累计购买上限100.00元)」-> 「暂停申购」"""
    if not status:
        return ""
    label = PAREN_RE.sub("", status).strip()
    return label or status.strip()


def is_buyable(status):
    """是否能买：只有「暂停申购」类状态不能买"""
    return "暂停" not in (status or "")


def effective_limit(status, amount):
    """有效额度：暂停申购时没有限额一说，返回 None"""
    return amount if is_buyable(status) else None


def _f(v):
    try:
        if v in (None, "", "--", "---"):
            return None
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- 抓取

def fetch_one(code, category=None):
    """抓取单只基金的全部字段"""
    out = {"code": code, "ok": False, "error": "", "category": category or DEFAULT_CATEGORY}

    # 1) 详情页：交易状态 + 单日限购额度
    try:
        html = _get(f"http://fund.eastmoney.com/{code}.html")
        sg, sh = parse_trade_status(html)
        lim_raw, lim_amt = parse_limit(sg)
        out["trade_status"] = sg
        out["redeem_status"] = sh
        out["limit_text"] = lim_raw
        out["limit_amount"] = lim_amt
    except Exception as e:  # noqa: BLE001
        out["error"] += f"详情页({e}); "

    # 2) pingzhongdata：基金名称 + 规模变动
    try:
        js = _get(f"http://fund.eastmoney.com/pingzhongdata/{code}.js")
        m = re.search(r'fS_name\s*=\s*"([^"]*)"', js)
        if m:
            out["fund_name"] = m.group(1)
        m = re.search(r"Data_fluctuationScale\s*=\s*(\{.*?\});", js, re.S)
        if m:
            data = json.loads(m.group(1))
            cats = data.get("categories") or []
            series = data.get("series") or []
            if cats and series:
                out["scale_date"] = cats[-1]
                out["scale_yi"] = series[-1].get("y")
                out["scale_series"] = [
                    (c, s.get("y"), s.get("mom", "")) for c, s in zip(cats, series)
                ]
    except Exception as e:  # noqa: BLE001
        out["error"] += f"规模({e}); "

    # 3) 历史净值：净值 / 涨幅 / 申购赎回状态兜底
    try:
        url = ("https://api.fund.eastmoney.com/f10/lsjz"
               f"?fundCode={code}&pageIndex=1&pageSize=8&startDate=&endDate="
               f"&_={int(time.time() * 1000)}")
        txt = _get(url, referer=f"https://fundf10.eastmoney.com/jjjz_{code}.html")
        data = json.loads(txt)
        lst = (data.get("Data") or {}).get("LSJZList") or []
        if lst:
            top = lst[0]
            out["nav"] = _f(top.get("DWJZ"))
            out["nav_date"] = top.get("FSRQ")
            out["day_growth"] = _f(top.get("JZZZL"))
            out["lsjz_status"] = (top.get("SGZT") or "", top.get("SHZT") or "")
            out["nav_list"] = [
                {"nav_date": x.get("FSRQ"), "nav": _f(x.get("DWJZ")), "growth": _f(x.get("JZZZL"))}
                for x in lst if x.get("FSRQ")
            ]
    except Exception as e:  # noqa: BLE001
        out["error"] += f"净值({e}); "

    out["ok"] = bool(out.get("trade_status") or out.get("nav") or out.get("fund_name"))
    return out


def fetch_all(funds=None, workers=8, progress=None):
    """并发抓取多只基金，返回结果列表（按传入顺序）

    funds: [{'code','category'}] 或 ['code', ...]；缺省读 funds.txt。
    """
    if funds is None:
        funds = load_funds()
    cmap = category_map()
    jobs = []
    for item in funds:
        if isinstance(item, dict):
            code = item.get("code")
            cat = item.get("category") or cmap.get(code) or DEFAULT_CATEGORY
        else:
            code = item
            cat = cmap.get(code) or DEFAULT_CATEGORY
        if code:
            jobs.append((code, cat))

    results = {}
    done = 0
    total = len(jobs)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_one, c, cat): c for c, cat in jobs}
        for fut in as_completed(futures):
            code = futures[fut]
            try:
                results[code] = fut.result()
            except Exception as e:  # noqa: BLE001
                results[code] = {"code": code, "ok": False, "error": str(e),
                                 "category": cmap.get(code) or DEFAULT_CATEGORY}
            done += 1
            if progress:
                progress(done, total, results[code])
    return [results[c] for c, _ in jobs if c in results]


if __name__ == "__main__":
    for r in fetch_all():
        print(r["code"], r.get("category"), r.get("fund_name"), "|",
              r.get("trade_status"), "|", r.get("limit_text"), "|",
              r.get("nav"), "|", r.get("scale_yi"))
