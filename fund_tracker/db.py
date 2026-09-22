# -*- coding: utf-8 -*-
"""SQLite 存储层：每日额度快照 / 净值历史 / 规模历史"""
import os
import sqlite3
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
DB_PATH = os.path.join(DATA_DIR, "funds.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS funds (
    code       TEXT PRIMARY KEY,
    name       TEXT,
    category   TEXT,                  -- 分类：标普 / 纳指100 / 纳指科技 / 主动
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS daily_record (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    code          TEXT    NOT NULL,
    snap_date     TEXT    NOT NULL,   -- 抓取当天日期 YYYY-MM-DD
    category      TEXT,               -- 分类（来自 funds.txt）
    fund_name     TEXT,
    trade_status  TEXT,               -- 申购状态，如 暂停申购 / 限大额 / 开放申购
    limit_text    TEXT,               -- 单日限购额度原文，如 100.00元
    limit_amount  REAL,               -- 归一化为“元”的额度数值
    redeem_status TEXT,               -- 赎回状态
    nav           REAL,               -- 单位净值
    nav_date      TEXT,               -- 净值日期
    day_growth    REAL,               -- 日涨幅 %
    scale_yi      REAL,               -- 最新规模（亿元）
    scale_date    TEXT,               -- 规模截止日
    created_at    TEXT,
    UNIQUE (code, snap_date)
);

CREATE TABLE IF NOT EXISTS nav_history (
    code     TEXT NOT NULL,
    nav_date TEXT NOT NULL,
    nav      REAL,
    growth   REAL,
    PRIMARY KEY (code, nav_date)
);

CREATE TABLE IF NOT EXISTS scale_history (
    code     TEXT NOT NULL,
    end_date TEXT NOT NULL,
    scale_yi REAL,
    mom      TEXT,
    PRIMARY KEY (code, end_date)
);

CREATE TABLE IF NOT EXISTS fetch_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at  TEXT,
    ok      INTEGER,
    failed  INTEGER,
    note    TEXT
);

CREATE INDEX IF NOT EXISTS idx_daily_code_date ON daily_record (code, snap_date DESC);
CREATE INDEX IF NOT EXISTS idx_daily_date      ON daily_record (snap_date DESC);
"""


def connect():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# 旧库补列（SQLite 不支持 ADD COLUMN IF NOT EXISTS，自己判断）
MIGRATIONS = [
    ("daily_record", "category", "TEXT"),
    ("funds", "category", "TEXT"),
]


def _migrate(conn):
    for table, column, coltype in MIGRATIONS:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if cols and column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


def init_db(sync_category=True):
    with connect() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
    if sync_category:
        # 分类以 funds.txt 为准：改了清单文件，库里已有记录的旧分类一并纠正
        try:
            import fetcher
            sync_categories(fetcher.category_map())
        except Exception:  # noqa: BLE001
            pass
    return DB_PATH


def sync_categories(cmap):
    """把 funds.txt 的分类回写到库里已存的记录（清单里没有的代码保持原值）

    分类是「每只基金」的属性，不是「每条记录」的属性，所以改清单后
    历史记录也应一起跟着变。返回被修正的行数。
    """
    if not cmap:
        return 0
    changed = 0
    with connect() as conn:
        for code, cat in cmap.items():
            if not cat:
                continue
            for table in ("daily_record", "funds"):
                cur = conn.execute(
                    f"UPDATE {table} SET category=? WHERE code=? "
                    f"AND IFNULL(category,'')<>?",
                    (cat, code, cat),
                )
                changed += cur.rowcount or 0
    return changed


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def save_results(results, snap_date=None):
    """results: fetcher.fetch_all() 的返回列表"""
    snap_date = snap_date or datetime.now().strftime("%Y-%m-%d")
    ok = failed = 0
    with connect() as conn:
        for r in results:
            code = r["code"]
            # 失败的抓取不落库，避免污染当日记录
            if not r.get("ok"):
                failed += 1
                continue
            ok += 1

            if r.get("fund_name"):
                conn.execute(
                    "INSERT INTO funds (code, name, category, updated_at) VALUES (?,?,?,?) "
                    "ON CONFLICT(code) DO UPDATE SET name=excluded.name, "
                    "category=excluded.category, updated_at=excluded.updated_at",
                    (code, r["fund_name"], r.get("category"), _now()),
                )
            # 页面解析失败时用行情接口的申购状态兜底
            trade_status = r.get("trade_status") or (r.get("lsjz_status") or ("", ""))[0]
            redeem_status = r.get("redeem_status") or (r.get("lsjz_status") or ("", ""))[1]

            conn.execute(
                """
                INSERT INTO daily_record
                    (code, snap_date, category, fund_name, trade_status, limit_text, limit_amount,
                     redeem_status, nav, nav_date, day_growth, scale_yi, scale_date, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(code, snap_date) DO UPDATE SET
                    category      = excluded.category,
                    fund_name     = excluded.fund_name,
                    trade_status  = excluded.trade_status,
                    limit_text    = excluded.limit_text,
                    limit_amount  = excluded.limit_amount,
                    redeem_status = excluded.redeem_status,
                    nav           = excluded.nav,
                    nav_date      = excluded.nav_date,
                    day_growth    = excluded.day_growth,
                    scale_yi      = excluded.scale_yi,
                    scale_date    = excluded.scale_date,
                    created_at    = excluded.created_at
                """,
                (code, snap_date, r.get("category"), r.get("fund_name"), trade_status,
                 r.get("limit_text") or "", r.get("limit_amount"),
                 redeem_status, r.get("nav"), r.get("nav_date"), r.get("day_growth"),
                 r.get("scale_yi"), r.get("scale_date"), _now()),
            )

            for n in r.get("nav_list") or []:
                if not n.get("nav_date"):
                    continue
                conn.execute(
                    "INSERT INTO nav_history (code, nav_date, nav, growth) VALUES (?,?,?,?) "
                    "ON CONFLICT(code, nav_date) DO UPDATE SET nav=excluded.nav, growth=excluded.growth",
                    (code, n["nav_date"], n.get("nav"), n.get("growth")),
                )

            for s in r.get("scale_series") or []:
                conn.execute(
                    "INSERT INTO scale_history (code, end_date, scale_yi, mom) VALUES (?,?,?,?) "
                    "ON CONFLICT(code, end_date) DO UPDATE SET scale_yi=excluded.scale_yi, mom=excluded.mom",
                    (code, s[0], s[1], s[2]),
                )

        conn.execute(
            "INSERT INTO fetch_log (run_at, ok, failed, note) VALUES (?,?,?,?)",
            (_now(), ok, failed, snap_date),
        )
    return {"ok": ok, "failed": failed, "date": snap_date}


# --------------------------------------------------------------------------- 查询

def latest_snapshot():
    """每只基金的最新一条记录（不限于今天）"""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT d.* FROM daily_record d
            JOIN (SELECT code, MAX(snap_date) mx FROM daily_record GROUP BY code) m
              ON d.code = m.code AND d.snap_date = m.mx
            ORDER BY d.code
            """
        ).fetchall()
    return [dict(r) for r in rows]


def previous_record(code, before_date):
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM daily_record WHERE code=? AND snap_date<? "
            "ORDER BY snap_date DESC LIMIT 1",
            (code, before_date),
        ).fetchone()
    return dict(row) if row else None


def history(code=None, days=365):
    sql = "SELECT * FROM daily_record WHERE 1=1"
    args = []
    if code:
        sql += " AND code=?"
        args.append(code)
    if days:
        sql += " AND snap_date >= date('now', ?)"
        args.append(f"-{int(days)} day")
    sql += " ORDER BY snap_date DESC, code ASC"
    with connect() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [dict(r) for r in rows]


def trend(code):
    """某只基金的额度/状态走势（按日期正序）"""
    with connect() as conn:
        rows = conn.execute(
            "SELECT snap_date, trade_status, limit_text, limit_amount, nav, day_growth, scale_yi "
            "FROM daily_record WHERE code=? ORDER BY snap_date ASC",
            (code,),
        ).fetchall()
    return [dict(r) for r in rows]


def last_fetch():
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM fetch_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def record_days():
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(DISTINCT snap_date) c, MIN(snap_date) mn, MAX(snap_date) mx FROM daily_record"
        ).fetchone()
    return dict(row) if row else {"c": 0, "mn": None, "mx": None}
