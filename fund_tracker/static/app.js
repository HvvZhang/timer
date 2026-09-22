/* 基金限购额度盯盘 —— 前端逻辑 */
(function () {
  "use strict";

  // ---------------------------------------------------------------- 工具
  const $ = (s) => document.querySelector(s);

  function fmtAmount(v) {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    if (!isFinite(n)) return "—";
    if (n >= 10000) return trimNum(n / 10000) + "万元";
    return trimNum(n) + "元";
  }
  function trimNum(n) {
    return (Math.round(n * 100) / 100).toString();
  }
  function fmtGrowth(v) {
    if (v === null || v === undefined || v === "") return '<span class="flat">—</span>';
    const n = Number(v);
    const cls = n > 0 ? "up" : (n < 0 ? "down" : "flat");
    const sign = n > 0 ? "+" : "";
    return `<span class="${cls}">${sign}${n.toFixed(2)}%</span>`;
  }
  /* 暂停申购 -> 红色；能买（限大额 / 开放申购）-> 绿色 */
  function statusClass(s) {
    if (!s) return "tag-other";
    if (s.indexOf("暂停") >= 0) return "tag-suspend";
    if (s.indexOf("限") >= 0 || s.indexOf("开放") >= 0) return "tag-buy";
    return "tag-other";
  }
  /* 额度变化方向：变大 -> chg-up（蓝），变小 -> chg-down（黄）；暂停申购按 0 计 */
  function changeClass(amountChanged, prevAmount, curAmount) {
    if (!amountChanged) return "";
    const pv = prevAmount === null || prevAmount === undefined ? 0 : Number(prevAmount);
    const cv = curAmount === null || curAmount === undefined ? 0 : Number(curAmount);
    return cv > pv ? "chg-up" : "chg-down";
  }
  function esc(s) {
    return String(s === null || s === undefined ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function shortName(n) {
    return String(n || "").replace(/\s+/g, " ").trim();
  }

  // ---------------------------------------------------------------- 总览表排序
  // 默认按「单日限购额度」从多到少；点击表头在升序 / 降序之间切换。
  const sortState = { key: "limit", dir: "desc" };
  let lastSnapshot = null;
  let catFilter = "全部";          // 分类筛选，默认「全部」= 全部显示
  const catRank = {};              // 分类名 -> 序号（用于排序稳定 + 标签配色）

  function catIndexOf(name) {
    return Object.prototype.hasOwnProperty.call(catRank, name) ? catRank[name] : 99;
  }

  const DIR_WORD = {
    limit:  { desc: "从多到少", asc: "从少到多" },
    change: { desc: "变大在前", asc: "变小在前" },
    growth: { desc: "涨幅高在前", asc: "涨幅低在前" },
    scale:  { desc: "规模大在前", asc: "规模小在前" },
  };

  /* 暂停申购没有额度，按 0 计（与配色口径一致：变暂停＝额度变小） */
  function limitOf(it) {
    const v = it.limit_amount;
    return v === null || v === undefined || !isFinite(Number(v)) ? 0 : Number(v);
  }

  function sortValue(it, key) {
    if (key === "limit") return limitOf(it);
    if (key === "change") {
      if (!it.amount_changed) return 0;         // 与上次一致 / 仅状态变
      return limitOf(it) - limitOf({ limit_amount: it.prev_limit_amount });
    }
    const v = it[key === "growth" ? "day_growth" : "scale_yi"];
    return v === null || v === undefined || v === "" || !isFinite(Number(v))
      ? null                                   // 空值：无论升降序都排最后
      : Number(v);
  }

  function applySort(items) {
    const key = sortState.key;
    const dir = sortState.dir === "asc" ? 1 : -1;
    return items.slice().sort((a, b) => {
      const va = sortValue(a, key), vb = sortValue(b, key);
      const na = va === null, nb = vb === null;
      if (na || nb) return na && nb ? 0 : (na ? 1 : -1);
      if (va === vb) {
        // 同值时按分类归拢，再按代码，避免刷新后顺序乱跳
        const ca = catIndexOf(a.category), cb = catIndexOf(b.category);
        if (ca !== cb) return ca - cb;
        return String(a.code).localeCompare(String(b.code));
      }
      return (va - vb) * dir;
    });
  }

  function markSortHeaders() {
    document.querySelectorAll("#tblOverview thead th.sortable").forEach((th) => {
      const on = th.getAttribute("data-sort") === sortState.key;
      th.classList.toggle("asc", on && sortState.dir === "asc");
      th.classList.toggle("desc", on && sortState.dir === "desc");
      if (!th.hasAttribute("data-title")) th.setAttribute("data-title", th.title);
      const base = th.getAttribute("data-title");
      if (on) {
        const w = (DIR_WORD[sortState.key] || {})[sortState.dir] || "";
        th.setAttribute("aria-sort", sortState.dir === "asc" ? "ascending" : "descending");
        th.title = `${base}（当前：${w}）`;
      } else {
        th.removeAttribute("aria-sort");
        th.title = base;
      }
    });
  }

  function bindSortHeaders() {
    document.querySelectorAll("#tblOverview thead th.sortable").forEach((th) => {
      th.addEventListener("click", () => {
        const key = th.getAttribute("data-sort");
        if (sortState.key === key) {
          sortState.dir = sortState.dir === "asc" ? "desc" : "asc";
        } else {
          sortState.key = key;
          sortState.dir = th.getAttribute("data-default") || "desc";
        }
        if (lastSnapshot) renderOverview(lastSnapshot);
      });
    });
  }

  // ---------------------------------------------------------------- 分类切换按钮
  /* 按钮由接口返回的分类清单生成（「全部」在最前），默认全部显示 */
  function renderCatBar(data) {
    const bar = $("#catBar");
    if (!bar) return;
    const cats = (data && data.categories) || [];
    if (!cats.length) { bar.innerHTML = ""; return; }
    if (!cats.some((c) => c.name === catFilter)) catFilter = cats[0].name;

    Object.keys(catRank).forEach((k) => { delete catRank[k]; });
    cats.filter((c) => c.name !== "全部").forEach((c, i) => { catRank[c.name] = i; });

    bar.innerHTML = cats.map((c) => {
      const on = c.name === catFilter ? " on" : "";
      return `<button type="button" class="cat-btn${on}" data-cat="${esc(c.name)}"`
           + ` title="切换到 ${esc(c.name)}">${esc(c.name)}<span class="n">${c.count}</span></button>`;
    }).join("");
  }

  // ---------------------------------------------------------------- 顶部状态
  async function loadSnapshot() {
    const res = await fetch("/api/snapshot");
    const data = await res.json();
    renderOverview(data);
    loadChanges();
    loadFundSelect();
    return data;
  }

  function renderOverview(data) {
    lastSnapshot = data;
    const tbody = $("#tblOverview tbody");
    const rawItems = data.items || [];
    renderCatBar(data);
    const items = applySort(rawItems.filter(
      (it) => catFilter === "全部" || it.category === catFilter
    ));
    $("#fundCount").textContent = rawItems.length;
    markSortHeaders();

    if (!items.length) {
      tbody.innerHTML = `<tr><td colspan="10"><div class="empty-tip">`
        + (rawItems.length
            ? `「${esc(catFilter)}」分类下暂无记录。`
            : `暂无记录，点击右上角「立即抓取」开始建立每日记录。`)
        + `</div></td></tr>`;
    } else {
      tbody.innerHTML = items.map((it) => {
        let changeCell = '<span class="flat">—</span>';
        if (it.changed) {
          const cls = changeClass(it.amount_changed, it.prev_limit_amount, it.limit_amount);
          changeCell = `<span class="${cls}">${esc(it.change_desc)}</span>`;
          if (it.prev_snap_date) {
            changeCell += `<div class="muted" style="font-size:12px">对比 ${esc(it.prev_snap_date)}</div>`;
          }
        } else if (it.prev_snap_date) {
          changeCell = '<span class="flat">与上次一致</span>';
        }
        return `<tr>
          <td class="code">${esc(it.code)}</td>
          <td>${esc(shortName(it.name))}${it.missing ? ' <span class="muted">(已从列表移除)</span>' : ""}</td>
          <td><span class="cat-tag cat-${catIndexOf(it.category)}">${esc(it.category || "—")}</span></td>
          <td><span class="status-tag ${statusClass(it.status_label)}">${esc(it.status_label || "—")}</span></td>
          <td class="num limit-strong">${esc(it.limit_display)}</td>
          <td>${changeCell}</td>
          <td class="num">${it.nav === null || it.nav === undefined ? "—" : Number(it.nav).toFixed(4)}</td>
          <td class="num">${fmtGrowth(it.day_growth)}</td>
          <td class="num">${it.scale_yi === null || it.scale_yi === undefined ? "—" : Number(it.scale_yi).toFixed(2)}</td>
          <td class="muted">${esc(it.nav_date || "—")}</td>
        </tr>`;
      }).join("");
    }

    const lf = data.last_fetch;
    const dot = $("#statusDot");
    const txt = $("#statusText");
    const st = data.state || {};
    if (st.running) {
      dot.className = "dot busy";
      txt.textContent = "正在抓取数据…";
      $("#btnFetch").disabled = true;
    } else if (lf) {
      dot.className = "dot ok";
      txt.textContent = `最近抓取：${lf.run_at}（成功 ${lf.ok} 只${lf.failed ? "，失败 " + lf.failed + " 只" : ""}）`;
      $("#btnFetch").disabled = false;
    } else {
      dot.className = "dot";
      txt.textContent = "尚未抓取过，请点击「立即抓取」";
      $("#btnFetch").disabled = false;
    }

    const rd = data.record_days || {};
    if (rd.c) {
      $("#recordInfo").textContent = `已累计 ${rd.c} 个交易日记录（${rd.mn} ~ ${rd.mx}）`;
    }
    const lastDate = rawItems.map((i) => i.snap_date || "").filter(Boolean).sort().slice(-1)[0] || "";
    $("#overviewDate").textContent = lastDate
      ? `记录日期 ${lastDate} ｜ 显示 ${items.length} / ${rawItems.length} 只`
      : "";
  }

  // ---------------------------------------------------------------- 变动提醒
  async function loadChanges() {
    const res = await fetch("/api/changes");
    const data = await res.json();
    const box = $("#changes");
    const items = data.items || [];
    if (!items.length) {
      box.innerHTML = '<div class="empty-tip">最近两次记录之间，额度与申购状态均无变化。</div>';
      return;
    }
    box.innerHTML = items.map((it) => {
      let rowCls = "status-row";
      let arrow;
      if (it.amount_changed) {
        rowCls = it.direction === "up" ? "up-row" : "down-row";
        arrow = `<span class="cflow">额度 <b>${esc(it.from_limit)}</b> → <b>${esc(it.to_limit)}</b>`
              + `<span class="muted">（${it.direction === "up" ? "变大" : "变小"}）</span></span>`;
      } else {
        arrow = `<span class="cflow">状态：${esc(it.from_status || "—")} → <b>${esc(it.to_status || "—")}</b></span>`;
      }
      return `<div class="change-row ${rowCls}">
        <span class="cname">${esc(it.code)} ${esc(shortName(it.name))}</span>
        ${arrow}
        <span class="cdate">${esc(it.prev_date)} → ${esc(it.snap_date)}</span>
      </div>`;
    }).join("");
  }

  // ---------------------------------------------------------------- 基金下拉（按分类分组）
  async function loadFundSelect() {
    const res = await fetch("/api/funds");
    const data = await res.json();
    const sel = $("#selFund");
    const keep = sel.value;

    const groups = [];
    const pos = {};
    (data.items || []).forEach((f) => {
      const c = f.category || "其他";
      if (!(c in pos)) { pos[c] = groups.length; groups.push({ name: c, items: [] }); }
      groups[pos[c]].items.push(f);
    });
    groups.sort((a, b) => catIndexOf(a.name) - catIndexOf(b.name));

    sel.innerHTML = groups.map((g) =>
      `<optgroup label="${esc(g.name)}（${g.items.length}）">`
      + g.items.map((f) => `<option value="${esc(f.code)}">${esc(f.code)} ${esc(shortName(f.name))}</option>`).join("")
      + `</optgroup>`
    ).join("");

    if (keep) sel.value = keep;
    loadHistory();
  }

  // ---------------------------------------------------------------- 历史 + 走势
  async function loadHistory() {
    const code = $("#selFund").value;
    const days = $("#selRange").value;
    if (!code) return;

    const [hRes, tRes] = await Promise.all([
      fetch(`/api/history?code=${encodeURIComponent(code)}&days=${days}`),
      fetch(`/api/trend?code=${encodeURIComponent(code)}`),
    ]);
    const hist = (await hRes.json()).items || [];
    const trend = (await tRes.json()).items || [];

    const tbody = $("#tblHistory tbody");
    if (!hist.length) {
      tbody.innerHTML = '<tr><td colspan="8"><div class="empty-tip">该基金暂无历史记录。</div></td></tr>';
    } else {
      tbody.innerHTML = hist.map((r) => `<tr>
        <td>${esc(r.snap_date)}</td>
        <td>${esc(r.code)} ${esc(shortName(r.fund_name))}</td>
        <td><span class="status-tag ${statusClass(r.status_label)}">${esc(r.status_label || "—")}</span></td>
        <td class="num limit-strong">${esc(r.limit_display || "—")}</td>
        <td class="num">${r.nav === null || r.nav === undefined ? "—" : Number(r.nav).toFixed(4)}</td>
        <td class="num">${fmtGrowth(r.day_growth)}</td>
        <td class="num">${r.scale_yi === null || r.scale_yi === undefined ? "—" : Number(r.scale_yi).toFixed(2)}</td>
        <td class="muted">${esc(r.nav_date || "—")}</td>
      </tr>`).join("");
    }

    renderTrend(trend, code);
  }

  /* 静态阶梯走势图（不依赖鼠标悬停，数值直接标注在图上）
     暂停申购当天没有额度，点画在坐标轴底端并标注「暂停」 */
  function renderTrend(items, code) {
    const box = $("#trend");
    if (!items || !items.length) {
      box.innerHTML = '<div class="empty-tip">暂无记录用于绘制走势。</div>';
      return;
    }

    const pts = items.slice();
    const buyVals = pts
      .filter((d) => d.eff_limit !== null && d.eff_limit !== undefined)
      .map((d) => Number(d.eff_limit));
    if (!buyVals.length) {
      box.innerHTML = '<div class="empty-tip">该基金全部记录均为「暂停申购」，没有限额可绘制。</div>';
      return;
    }

    const W = 1060, H = 260;
    const padL = 78, padR = 40, padT = 36, padB = 46;
    const iw = W - padL - padR, ih = H - padT - padB;

    const maxV = Math.max.apply(null, buyVals);
    const minV = Math.min.apply(null, buyVals);
    // 跨度大时用对数刻度，避免 10 元 与 1 万元 无法同图比较
    const useLog = minV > 0 && maxV / minV >= 8;
    const yMin = useLog ? Math.log10(Math.max(minV * 0.6, 0.5)) : 0;
    const yMax = useLog ? Math.log10(maxV * 1.4) : maxV * 1.2;
    const baseY = padT + ih;                     // 暂停申购点落在这里
    const isBuy = (d) => d.eff_limit !== null && d.eff_limit !== undefined;
    const toY = (v) => {
      const t = useLog
        ? (Math.log10(Math.max(v, 0.5)) - yMin) / (yMax - yMin)
        : (v - yMin) / (yMax - yMin);
      return baseY - t * ih;
    };
    const np = pts.length;
    const toX = (i) => (np === 1 ? padL + iw / 2 : padL + (i * iw) / (np - 1));

    let s = "";
    // 网格 + Y 轴刻度
    for (let k = 0; k <= 4; k++) {
      const t = k / 4;
      const v = useLog ? Math.pow(10, yMin + t * (yMax - yMin)) : yMin + t * (yMax - yMin);
      const y = toY(v).toFixed(1);
      s += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="#eef1f6" stroke-width="1"/>`;
      s += `<text x="${padL - 10}" y="${Number(y) + 4}" text-anchor="end" font-size="11" fill="#8b93a1">${k === 0 && !useLog ? "0元" : fmtAmount(v)}</text>`;
    }

    const yOf = (i) => (isBuy(pts[i]) ? toY(Number(pts[i].eff_limit)) : baseY);

    // 阶梯线
    let d = "";
    pts.forEach((p, i) => {
      const x = toX(i);
      if (i === 0) d += `M ${x} ${yOf(i)}`;
      else d += ` L ${x} ${yOf(i - 1)} L ${x} ${yOf(i)}`;
    });
    s += `<path d="${d}" fill="none" stroke="#2563eb" stroke-width="2"/>`;

    // 数据点 + 数值标注（绿＝当日可申购，红＝当日暂停申购）
    const step = np > 14 ? Math.ceil(np / 14) : 1;
    pts.forEach((p, i) => {
      const x = toX(i), y = yOf(i), ok = isBuy(p);
      const color = ok ? "#16a34a" : "#dc2626";
      s += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4" fill="#fff" stroke="${color}" stroke-width="2"/>`;
      if (i % step === 0 || i === np - 1) {
        const label = ok ? fmtAmount(p.eff_limit) : "暂停";
        s += `<text x="${x.toFixed(1)}" y="${(y - 11).toFixed(1)}" text-anchor="middle" font-size="11" font-weight="700" fill="${ok ? "#1f2937" : "#dc2626"}">${label}</text>`;
        s += `<text x="${x.toFixed(1)}" y="${H - padB + 18}" text-anchor="middle" font-size="10" fill="#8b93a1">${esc((p.snap_date || "").slice(5))}</text>`;
      }
    });

    box.innerHTML =
      `<div class="trend-title">${esc(code)} 单日限购额度走势（共 ${np} 条记录，纵轴${useLog ? "为对数刻度" : "为线性刻度"}；<span style="color:#16a34a">绿色点＝当日可申购</span>，<span style="color:#dc2626">红色点＝当日暂停申购（无额度）</span>）</div>
       <svg class="trend-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" role="img"
            aria-label="${esc(code)} 限购额度走势图">
         <rect x="0" y="0" width="${W}" height="${H}" fill="#ffffff"/>
         ${s}
       </svg>`;
  }

  // ---------------------------------------------------------------- 交互
  $("#btnFetch").addEventListener("click", async () => {
    $("#btnFetch").disabled = true;
    $("#statusDot").className = "dot busy";
    $("#statusText").textContent = "正在抓取数据，请稍候…";
    try {
      const res = await fetch("/api/fetch", { method: "POST" });
      const data = await res.json();
      if (!data.ok) {
        $("#statusText").textContent = data.message || "抓取失败";
        $("#statusDot").className = "dot err";
        $("#btnFetch").disabled = false;
        return;
      }
      pollFetch();
    } catch (e) {
      $("#statusText").textContent = "请求失败：" + e;
      $("#statusDot").className = "dot err";
      $("#btnFetch").disabled = false;
    }
  });

  function pollFetch() {
    let tries = 0;
    const timer = setInterval(async () => {
      tries++;
      try {
        const st = await (await fetch("/api/fetch_status")).json();
        if (!st.running) {
          clearInterval(timer);
          await loadSnapshot();
          return;
        }
      } catch (e) { /* 继续轮询 */ }
      if (tries > 180) {
        clearInterval(timer);
        $("#statusText").textContent = "抓取超时，请刷新页面查看";
        $("#btnFetch").disabled = false;
      }
    }, 2000);
  }

  $("#btnExport").addEventListener("click", () => {
    const code = $("#selFund").value || "";
    const days = $("#selRange").value || "0";
    window.location.href = `/api/export?code=${encodeURIComponent(code)}&days=${days}`;
  });

  $("#selFund").addEventListener("change", loadHistory);
  $("#selRange").addEventListener("change", loadHistory);

  // 分类切换：点按钮只过滤显示，不重新请求接口
  $("#catBar").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-cat]");
    if (!btn) return;
    const name = btn.getAttribute("data-cat");
    if (name === catFilter) return;
    catFilter = name;
    if (lastSnapshot) renderOverview(lastSnapshot);
  });

  // 首次加载
  bindSortHeaders();
  loadSnapshot();
  setInterval(() => {
    fetch("/api/fetch_status").then((r) => r.json()).then((st) => {
      if (!st.running && $("#btnFetch").disabled === true) {
        loadSnapshot();
      }
    }).catch(() => {});
  }, 30000);
})();
