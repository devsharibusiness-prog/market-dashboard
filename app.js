(function () {
  "use strict";

  var DATA = null, SUG = null, MKT = null;
  var st = { sig: "all", cap: "all", srch: "", bk: "swing", shz: "all", nt: "news" };

  // ---------- theme ----------
  var tb = document.getElementById("theme");
  function ap(t) { document.documentElement.setAttribute("data-theme", t === "light" ? "light" : ""); tb.textContent = t === "light" ? "🌙" : "☀️"; }
  var sv = null; try { sv = localStorage.getItem("dt"); } catch (e) {}
  if (!sv) { sv = "dark"; }
  ap(sv);
  tb.addEventListener("click", function () {
    var c = document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
    var x = c === "light" ? "dark" : "light"; ap(x); try { localStorage.setItem("dt", x); } catch (e) {}
  });

  // ---------- helpers ----------
  var EM = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  function esc(s) { if (s == null) { return ""; } return String(s).split("").map(function (c) { return EM[c] || c; }).join(""); }
  function num(v) { return (v == null || isNaN(v)) ? null : Number(v); }
  function mon(v) { return (v == null || isNaN(v)) ? "—" : "$" + Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
  function cl(x, a, b) { return Math.max(a, Math.min(b, x)); }
  function pc(v) { return v == null ? "—" : (v > 0 ? "+" : "") + Number(v).toFixed(1) + "%"; }
  function fmt(v, d) { if (v == null || isNaN(v)) { return "—"; } return Number(v).toFixed(d === 0 ? 0 : 2); }
  function cc(t) { return ({ Mega: 1, Large: 1, Mid: 1, Small: 1, Unknown: 1 }[t]) ? t : "Unknown"; }
  function sc2(s) { return s === "keeper" ? "sig-keeper" : s === "dip-risk" ? "sig-dip-risk" : "sig-watch"; }
  function ms(tk) { return !st.srch || String(tk || "").toUpperCase().indexOf(st.srch.toUpperCase()) !== -1; }
  function pcap(t) { return st.cap === "all" || cc(t) === st.cap; }
  function psig(s) { return st.sig === "all" || s === st.sig; }
  function cb(t, m) { var c = cc(t); return '<span class="cap cap-' + c + '">' + esc(c) + '</span>' + (m ? '<span class="mcap">' + esc(m) + '</span>' : ''); }
  function si(tk) { if (!SUG || !SUG.suggestions) { return null; } var r = null; SUG.suggestions.forEach(function (x) { if (x.ticker === tk) { r = x; } }); return r; }
  function qo(tk) { var r = null; if (DATA && DATA.quotes) { DATA.quotes.forEach(function (x) { if (x.ticker === tk) { r = x; } }); } return r; }

  function spark(a) {
    if (!a || a.length < 2) { return ""; }
    var w = 90, h = 26, mn = Math.min.apply(null, a), mx = Math.max.apply(null, a), rg = (mx - mn) || 1;
    var p = a.map(function (v, i) { var x = (i / (a.length - 1)) * w; var y = h - ((v - mn) / rg) * h; return x.toFixed(1) + "," + y.toFixed(1); }).join(" ");
    var up = a[a.length - 1] >= a[0];
    return '<svg class="spark" width="' + w + '" height="' + h + '"><polyline points="' + p + '" fill="none" stroke="' + (up ? "var(--green)" : "var(--red)") + '" stroke-width="2"/></svg>';
  }
  function bar(l, v, c) { var x = v == null ? 0 : cl(v, 0, 100); return '<div class="subbar"><div class="sl"><span>' + esc(l) + '</span><span>' + (v == null ? "—" : Math.round(v)) + '</span></div><div class="track"><div class="fill ' + c + '" style="width:' + x + '%"></div></div></div>'; }
  function mcell(k, v, c) { return '<div class="metric"><div class="k">' + esc(k) + '</div><div class="v ' + (c || "") + '">' + v + '</div></div>'; }

  // ---------- market / daily brief ----------
  function rmkt() {
    var rg = document.getElementById("regime"), mk = document.getElementById("mkt");
    document.getElementById("brief").innerHTML = esc((DATA && DATA.brief) || "Loading...").split(String.fromCharCode(10)).join("<br>");
    if (!MKT) { rg.innerHTML = ""; mk.innerHTML = ""; return; }
    var r = MKT.regime || "unknown";
    var rc = r === "trend" ? "trend" : r === "range" ? "range" : r === "volatile" ? "volatile" : "unknown";
    var re = r === "trend" ? "📈" : r === "range" ? "↔️" : r === "volatile" ? "⚡" : "🧭";
    document.getElementById("mood").textContent = re;
    rg.innerHTML = '<span class="regime ' + rc + '">' + re + ' ' + esc(r) + ' market</span>' + (MKT.regime_reason ? '<div style="font-size:.74rem;color:var(--soft);margin-bottom:8px">' + esc(MKT.regime_reason) + '</div>' : '');
    var b = "";
    if (MKT.vix != null) { b += '<div class="mbox"><div class="l">VIX</div><div class="v vix-' + esc(MKT.vix_label || "normal") + '">' + fmt(MKT.vix) + '</div><div class="s">' + esc(MKT.vix_label || "") + '</div></div>'; }
    if (MKT.fear_greed_proxy != null) { var fg = cl(MKT.fear_greed_proxy, 0, 100); b += '<div class="mbox"><div class="l">Fear &amp; Greed (proxy)</div><div class="v">' + fg + ' <span style="font-size:.8rem;color:var(--muted)">' + esc(MKT.fg_label || "") + '</span></div><div class="fg"><div class="m" style="margin-left:calc(' + fg + '% - 6px)"></div></div></div>'; }
    if (MKT.key_spy_level) { var k = MKT.key_spy_level; b += '<div class="mbox"><div class="l">S&amp;P (SPY) level</div><div class="v">' + mon(k.level) + '</div><div class="s">' + esc(k.kind) + ' · ' + pc(k.distance_pct) + ' away</div></div>'; }
    var ld = (MKT.top2_leading || []).map(function (s) { return '<span class="schip lead">' + esc(s.etf) + ' ' + pc(s.ret_1m) + '</span>'; }).join("");
    var lg = (MKT.top2_lagging || []).map(function (s) { return '<span class="schip lag">' + esc(s.etf) + ' ' + pc(s.ret_1m) + '</span>'; }).join("");
    if (ld || lg) { b += '<div class="mbox" style="grid-column:span 2"><div class="l">Sectors (1-month)</div><div class="sect">' + ld + lg + '</div><div class="s" style="margin-top:5px">green=leading · red=lagging</div></div>'; }
    mk.innerHTML = b;
  }

  // ---------- modal ----------
  function open(tk) {
    var rec = si(tk), sc = DATA && DATA.screenIndex ? DATA.screenIndex[tk] : null, q = qo(tk);
    document.getElementById("mTitle").textContent = tk;
    var sb = []; if (q) { sb.push(mon(q.price)); if (q.change_pct != null) { sb.push(pc(q.change_pct)); } } if (sc) { sb.push(cc(sc.cap_tier) + " cap"); }
    document.getElementById("mSub").textContent = sb.join("  ·  ");
    var y = "";
    if (rec) {
      y += '<div class="msc"><div class="b"><div class="v">' + rec.total_score + '</div><div class="l">Total /100</div></div><div class="b"><div class="v" style="color:var(--accent)">' + rec.confidence_pct + '%</div><div class="l">Confidence</div></div><div class="b"><div class="v">' + esc(rec.setup_grade) + '</div><div class="l">Grade</div></div></div>';
      y += '<div class="msec"><h4>🧮 Score Breakdown</h4>' + bar("RSI", rec.rsi_score, "f-rsi") + bar("Momentum", rec.momentum_score, "f-mom") + bar("Fundamentals", rec.fundamental_subscore, "f-fund") + bar("Volume", rec.volume_score, "f-vol") + '</div>';
      y += '<div class="mhint">' + esc(rec.conviction_emoji) + ' <b>' + esc(rec.conviction) + '</b> · ' + esc(rec.horizon) + ' · ⏱️ ' + esc(rec.expected_window) + '<br>🎯 Trigger: <b>' + esc(rec.trigger) + '</b>' + (rec.backtest_winrate != null ? '<br>📊 Backtest: <b>' + rec.backtest_winrate + '% win</b> (' + esc(rec.backtest_note) + ') — PAST frequency, not a prediction' : '') + '</div>';
    }
    var t = rec && rec.technicals ? rec.technicals : {};
    y += '<div class="msec"><h4>📊 Technical</h4>';
    if (rec) {
      var rv = num(t.rsi), rcl = rv == null ? "" : rv >= 70 ? "bad" : rv <= 30 ? "good" : "";
      var m1 = num(t.mom_1m), m3 = num(t.mom_3m);
      y += '<div class="metrics">' + mcell("RSI", fmt(t.rsi), rcl) + mcell("50MA", mon(t.ma50)) + mcell("200MA", mon(t.ma200)) + mcell("1M", pc(m1), m1 == null ? "" : m1 > 0 ? "good" : "bad") + mcell("3M", pc(m3), m3 == null ? "" : m3 > 0 ? "good" : "bad") + mcell("52w Pos", fmt(t.pos_52w, 0) + "%") + mcell("ATR", mon(t.atr)) + mcell("Volatility", fmt(t.volatility) + "%") + mcell("Volume", (t.volume_ratio == null ? "—" : t.volume_ratio + "x"), t.volume_ratio >= 1.4 ? "good" : "") + mcell("vs " + esc(t.sector_etf || "sec"), pc(t.sector_rel), t.sector_rel == null ? "" : t.sector_rel > 0 ? "good" : "bad") + '</div>';
      if (rec.tech_notes && rec.tech_notes.length) { y += '<ul class="notelist">' + rec.tech_notes.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join("") + '</ul>'; }
    } else if (sc) {
      y += '<div class="metrics">' + mcell("RSI", fmt(sc.rsi)) + mcell("52w Pos", fmt(sc.pos_52w_pct, 0) + "%") + mcell("vs 200MA", pc(sc.vs_200ma), sc.vs_200ma > 0 ? "good" : "bad") + mcell("Signal", esc(sc.signal || "—")) + '</div><div class="mhint">Run suggest.py for full scores on this ticker.</div>';
    } else {
      y += '<div class="nodata">No technical data.</div>';
    }
    y += '</div>';
    y += '<div class="msec"><h4>🏛️ Fundamental</h4>';
    if (rec && rec.fundamentals) {
      var f = rec.fundamentals;
      var pe = num(f.pe), rg2 = num(f.rev_growth), mg = num(f.margin), roe = num(f.roe), de = num(f.debt_to_equity);
      y += '<div class="metrics">' + mcell("P/E", fmt(f.pe), pe == null ? "" : pe > 0 && pe < 25 ? "good" : pe > 40 ? "bad" : "") + mcell("Rev Growth", pc(rg2), rg2 == null ? "" : rg2 > 0 ? "good" : "bad") + mcell("Margin", (mg == null ? "—" : mg + "%"), mg == null ? "" : mg > 10 ? "good" : mg < 0 ? "bad" : "") + mcell("ROE", (roe == null ? "—" : roe + "%"), roe == null ? "" : roe > 15 ? "good" : roe < 0 ? "bad" : "") + mcell("Debt/Eq", fmt(f.debt_to_equity), de == null ? "" : de < 100 ? "good" : de > 200 ? "bad" : "") + mcell("Fwd EPS", fmt(f.eps_estimate)) + '</div>';
      if (rec.fund_notes && rec.fund_notes.length) { y += '<ul class="notelist">' + rec.fund_notes.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join("") + '</ul>'; }
    } else {
      y += '<div class="nodata">No fundamental data.</div>';
    }
    y += '</div><div class="mhint">⚠️ Not financial advice. Rule-based metrics + historical stats for research only.</div>';
    document.getElementById("mBody").innerHTML = y;
    document.getElementById("mbg").classList.add("open");
  }
  function close() { document.getElementById("mbg").classList.remove("open"); }
  document.getElementById("mClose").addEventListener("click", close);
  document.getElementById("mbg").addEventListener("click", function (e) { if (e.target === this) { close(); } });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") { close(); } });

  // ---------- card builders ----------
  function qcard(q) {
    var cp = num(q.change_pct), d = cp === null ? "flat" : cp > 0 ? "up" : cp < 0 ? "down" : "flat";
    var ar = d === "up" ? "▲" : d === "down" ? "▼" : "■", tx = cp === null ? "—" : (cp > 0 ? "+" : "") + cp.toFixed(2) + "%";
    var rec = si(q.ticker), t = rec && rec.technicals ? rec.technicals : {}, sp = spark(t.sparkline);
    var rl = ""; if (t.sector_rel != null) { rl = '<span class="relb ' + (t.sector_rel > 0 ? "rel-out" : "rel-under") + '">' + pc(t.sector_rel) + ' vs ' + esc(t.sector_etf || "sec") + '</span>'; } else { rl = '<span class="relb rel-na">sector n/a</span>'; }
    var vo = ""; if (t.volume_ratio != null) { vo = '<span class="volb' + (t.volume_ratio >= 1.4 ? " hot" : "") + '">' + t.volume_ratio + 'x vol</span>'; }
    var pp = num(t.pos_52w); pp = pp == null ? 50 : cl(pp, 0, 100);
    return '<div class="card" data-tk="' + esc(q.ticker) + '"><div class="trow"><span class="tkr">' + esc(q.ticker) + '</span><span class="chg ' + d + ' tnum">' + ar + ' ' + tx + '</span></div><div class="price tnum">' + mon(q.price) + '</div>' + sp + '<div class="relrow">' + rl + vo + '</div><div class="distbar"><div class="m" style="left:' + pp + '%"></div></div><div class="ends"><span>52w low</span><span>52w high</span></div><div class="meta">' + cb(q.cap_tier, q.market_cap_str) + '</div></div>';
  }
  function rrc(rr) { if (rr == null || isNaN(rr)) { return "rr-mid"; } if (rr >= 2) { return "rr-good"; } if (rr >= 1) { return "rr-mid"; } return "rr-bad"; }
  function tcard(t) {
    var b = t.buckets && t.buckets[st.bk], sc = DATA.screenIndex && DATA.screenIndex[t.ticker], rec = si(t.ticker);
    var ch = sc ? cb(sc.cap_tier, sc.market_cap_str) : "";
    var gr = rec && rec.setup_grade ? '<span class="grade grade-' + esc(rec.setup_grade) + '">' + esc(rec.setup_grade) + '</span>' : "";
    if (!b) { return '<div class="tcard" data-tk="' + esc(t.ticker) + '"><div class="ttop"><div class="ttl"><span class="tkr">' + esc(t.ticker) + '</span></div></div><div class="empty" style="border:none;padding:14px 0">No setup</div></div>'; }
    var en = num(b.entry), tg = num(b.target), sp = num(b.stop), rr = num(b.rr);
    var lo = Math.min(sp, tg, en), hi = Math.max(sp, tg, en), span = (hi - lo) || 1;
    function p(v) { return cl(((v - lo) / span) * 100, 0, 100); }
    var bk = ""; if (rec && rec.breakout_level != null) { bk = '<div class="brk">Breakout: <b>' + mon(rec.breakout_level) + '</b> (' + pc(rec.breakout_distance_pct) + ' away)</div>'; }
    return '<div class="tcard" data-tk="' + esc(t.ticker) + '"><div class="ttop"><div class="ttl"><span class="tkr">' + esc(t.ticker) + '</span>' + gr + '<span class="atr tnum">ATR ' + mon(t.atr) + '</span></div><span class="rr ' + rrc(rr) + ' tnum">1:' + (rr === null ? "—" : rr.toFixed(1)) + '</span></div>' + (ch ? '<div class="meta">' + ch + '</div>' : '') + '<div class="ets"><div class="ebox e-stop"><div class="elabel">Stop</div><div class="eval tnum">' + mon(sp) + '</div></div><div class="ebox e-entry"><div class="elabel">Entry</div><div class="eval tnum">' + mon(en) + '</div></div><div class="ebox e-target"><div class="elabel">Target</div><div class="eval tnum">' + mon(tg) + '</div></div></div><div class="rrbar"><div class="rrm s" style="left:' + p(sp) + '%"></div><div class="rrm e" style="left:' + p(en) + '%"></div><div class="rrm t" style="left:' + p(tg) + '%"></div></div><div class="rrends"><span class="s">◄ Stop</span><span class="e">Entry</span><span class="t">Target ►</span></div>' + bk + '</div>';
  }
  function sgcard(r) {
    var cf = cl(r.confidence_pct || 0, 0, 100);
    var wn = r.backtest_winrate != null ? '<span class="winb">📊 ' + r.backtest_winrate + '% (' + r.backtest_sample + ')</span>' : "";
    return '<div class="sug ' + esc(r.conviction) + '" data-tk="' + esc(r.ticker) + '"><div class="sugtop"><span class="tkr">' + esc(r.ticker) + '</span><span class="sugsc">' + r.total_score + '<span style="font-size:.8rem;color:var(--soft)">/100</span></span></div>' + bar("RSI", r.rsi_score, "f-rsi") + bar("Momentum", r.momentum_score, "f-mom") + bar("Fundamentals", r.fundamental_subscore, "f-fund") + bar("Volume", r.volume_score, "f-vol") + '<div class="subbar"><div class="sl"><span>Confidence</span><span>' + cf + '%</span></div><div class="confbar"><div class="conff" style="width:' + cf + '%"></div></div></div><div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:9px"><span class="hzn">' + esc(r.horizon) + '</span><span>' + esc(r.conviction_emoji) + ' ' + esc(r.conviction) + '</span></div><div class="trig">🎯 ' + esc(r.trigger) + '</div> ' + wn + '<div class="win">⏱️ ' + esc(r.expected_window) + '</div></div>';
  }

  // ---------- renderers ----------
  function rsug() {
    var g = document.getElementById("sugGrid"); if (!g) { return; }
    if (!SUG || !SUG.suggestions || !SUG.suggestions.length) { g.innerHTML = '<div class="empty"><span class="em">💡</span>No suggestions - run suggest.py.</div>'; document.getElementById("sugSub").textContent = ""; return; }
    var l = SUG.suggestions.filter(function (r) { return ms(r.ticker) && (st.shz === "all" || r.horizon === st.shz); });
    document.getElementById("sugSub").textContent = l.length + " ranked · click for analysis";
    g.innerHTML = l.length ? l.map(sgcard).join("") : '<div class="empty"><span class="em">💡</span>No matches.</div>';
  }
  function rq() {
    var g = document.getElementById("qGrid");
    var l = (DATA.quotes || []).filter(function (q) { if (!ms(q.ticker)) { return false; } if (!pcap(q.cap_tier)) { return false; } if (st.sig !== "all") { var sc = DATA.screenIndex[q.ticker]; if (!sc || !psig(sc.signal)) { return false; } } return true; });
    l.sort(function (a, b) { return String(a.ticker).localeCompare(String(b.ticker)); });
    document.getElementById("qSub").textContent = l.length + " symbols";
    g.innerHTML = l.length ? l.map(qcard).join("") : '<div class="empty"><span class="em">📭</span>No quotes match.</div>';
  }
  function rtr() {
    var g = document.getElementById("trGrid");
    var l = (DATA.trades || []).filter(function (t) { if (!ms(t.ticker)) { return false; } var sc = DATA.screenIndex[t.ticker]; if (st.cap !== "all" && (!sc || !pcap(sc.cap_tier))) { return false; } if (st.sig !== "all" && (!sc || !psig(sc.signal))) { return false; } return true; });
    l.sort(function (a, b) { return String(a.ticker).localeCompare(String(b.ticker)); });
    g.innerHTML = l.length ? l.map(tcard).join("") : '<div class="empty"><span class="em">🎯</span>No setups match.</div>';
  }
  function re() {
    var el = document.getElementById("eList");
    var l = (DATA.earnings || []).filter(function (e) { return ms(e.ticker); });
    if (!l.length) { el.innerHTML = '<div class="empty"><span class="em">📅</span>No upcoming earnings.</div>'; return; }
    var td = new Date(); td.setHours(0, 0, 0, 0);
    var M = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    l.sort(function (a, b) { return new Date(a.date) - new Date(b.date); });
    el.innerHTML = l.map(function (e) {
      var dt = new Date(e.date), ok = !isNaN(dt.getTime());
      var df = ok ? Math.round((new Date(dt.getFullYear(), dt.getMonth(), dt.getDate()) - td) / 864e5) : null;
      var cls = "", tx = "";
      if (df === null) { tx = "—"; } else if (df < 0) { cls = "past"; tx = Math.abs(df) + "d ago"; }
      else if (df === 0) { cls = "today"; tx = "Today"; } else if (df <= 7) { cls = "soon"; tx = "in " + df + "d"; } else { tx = "in " + df + "d"; }
      var rec = si(e.ticker), f = rec && rec.fundamentals ? rec.fundamentals : {};
      var stk = "";
      if (f.earnings_streak && f.earnings_streak.length) {
        stk = '<span class="streak">' + f.earnings_streak.map(function (s) { var c = s === "beat" ? "beat" : s === "miss" ? "miss" : s === "in-line" ? "inline" : "na"; return '<span class="sb ' + c + '">' + esc(s) + '</span>'; }).join("") + '</span>';
      }
      var stats = '<div class="estats">' + (f.eps_estimate != null ? '<div class="estat"><div class="k">Fwd EPS</div><div class="v">' + fmt(f.eps_estimate) + '</div></div>' : '') + (f.avg_post_earnings_move_pct != null ? '<div class="estat"><div class="k">Avg Move</div><div class="v">±' + f.avg_post_earnings_move_pct + '%</div></div>' : '') + (stk ? '<div class="estat"><div class="k">Last 4Q</div><div class="v">' + stk + '</div></div>' : '') + '</div>';
      return '<div class="eli"><div class="elitop"><div class="eld"><span class="d tnum">' + (ok ? dt.getDate() : "?") + '</span><span class="m">' + (ok ? M[dt.getMonth()] : "") + '</span></div><span class="elt">' + esc(e.ticker) + '</span><span class="elc ' + cls + '">' + tx + '</span></div>' + stats + '</div>';
    }).join("");
  }
  function nic(u, h) { u = (u || "").toLowerCase(); h = (h || "").toLowerCase(); if (u.indexOf("sec.gov") !== -1 || h.indexOf("8-k") !== -1 || h.indexOf("filing") !== -1) { return "📄"; } if (h.indexOf("earnings") !== -1) { return "💰"; } return "📰"; }
  function host(u) { try { var a = document.createElement("a"); a.href = u; var h = a.hostname; if (h.indexOf("www.") === 0) { h = h.slice(4); } return h; } catch (e) { return ""; } }
  function isFiling(n) { var u = (n.url || "").toLowerCase(), h = (n.headline || "").toLowerCase(); return u.indexOf("sec.gov") !== -1 || h.indexOf("8-k") !== -1 || h.indexOf("filing") !== -1; }
  function sentOf(tk) { var r = si(tk); if (r && r.sentiment && r.sentiment.label) { return r.sentiment.label; } return null; }
  function rn() {
    var el = document.getElementById("nList");
    var all = (DATA.news || []);
    var l = all.filter(function (n) { var f = isFiling(n); return st.nt === "filings" ? f : !f; });
    if (!l.length) { el.innerHTML = '<div class="empty"><span class="em">📰</span>No ' + st.nt + '.</div>'; return; }
    el.innerHTML = l.map(function (n) {
      var h = host(n.url || "");
      var tkm = (n.headline || "").split(" ")[0];
      var s = sentOf(tkm);
      var sc = s ? '<span class="sent sent-' + s + '">' + esc(s) + ' (keyword)</span>' : "";
      return '<a class="ncard" href="' + esc(n.url || "#") + '" target="_blank" rel="noopener"><span class="nic">' + nic(n.url, n.headline) + '</span><span><span class="nhead">' + esc(n.headline) + '</span>' + (h ? '<span class="nurl">' + esc(h) + '</span>' : '') + sc + '</span></a>';
    }).join("");
  }
  function rfresh() {
    var d = document.getElementById("fd"), t = document.getElementById("ft");
    var g = DATA && DATA.generated_at ? new Date(DATA.generated_at) : null;
    if (!g || isNaN(g.getTime())) { d.className = "dot dead"; t.textContent = "Unknown"; return; }
    var m = Math.round((Date.now() - g.getTime()) / 6e4);
    d.className = "dot" + (m > 30 ? " dead" : m > 10 ? " stale" : "");
    t.textContent = "Updated " + (m < 1 ? "just now" : m < 60 ? m + "m ago" : Math.floor(m / 60) + "h ago");
  }
  function rall() {
    if (DATA) {
      DATA.screenIndex = {};
      (DATA.screen || []).forEach(function (s) { DATA.screenIndex[s.ticker] = s; });
      rq(); rtr(); re(); rn(); rfresh();
    }
    rmkt(); rsug();
  }

  // ---------- loaders ----------
  function err(m) { document.getElementById("err").innerHTML = '<div class="errbox">⚠️ ' + esc(m) + '</div>'; }
  function ld() {
    fetch("data.json?_=" + Date.now(), { cache: "no-store" })
      .then(function (r) { if (!r.ok) { throw new Error("HTTP " + r.status); } return r.json(); })
      .then(function (j) { DATA = j || {}; document.getElementById("err").innerHTML = ""; rall(); })
      .catch(function (e) { err("Could not load data.json - " + (e && e.message ? e.message : "err")); var d = document.getElementById("fd"); if (d) { d.className = "dot dead"; } });
  }
  function lsug() {
    fetch("suggestions.json?_=" + Date.now(), { cache: "no-store" })
      .then(function (r) { if (!r.ok) { throw new Error("x"); } return r.json(); })
      .then(function (j) { SUG = j; rall(); })
      .catch(function (e) { var g = document.getElementById("sugGrid"); if (g) { g.innerHTML = '<div class="empty"><span class="em">💡</span>suggestions.json not found - run suggest.py.</div>'; } });
  }
  function lmkt() {
    fetch("market.json?_=" + Date.now(), { cache: "no-store" })
      .then(function (r) { if (!r.ok) { throw new Error("x"); } return r.json(); })
      .then(function (j) { MKT = j; rmkt(); })
      .catch(function (e) {});
  }

  // ---------- events ----------
  document.getElementById("refresh").addEventListener("click", function () { ld(); lsug(); lmkt(); });
  document.getElementById("srch").addEventListener("input", function (e) { st.srch = e.target.value.trim(); rall(); });
  document.querySelectorAll(".fchip[data-sig]").forEach(function (c) { c.addEventListener("click", function () { st.sig = c.getAttribute("data-sig"); document.querySelectorAll(".fchip[data-sig]").forEach(function (x) { x.classList.toggle("active", x === c); }); rall(); }); });
  document.querySelectorAll(".fchip[data-cap]").forEach(function (c) { c.addEventListener("click", function () { st.cap = c.getAttribute("data-cap"); document.querySelectorAll(".fchip[data-cap]").forEach(function (x) { x.classList.toggle("active", x === c); }); rall(); }); });
  document.querySelectorAll(".ttab[data-bk]").forEach(function (b) { b.addEventListener("click", function () { st.bk = b.getAttribute("data-bk"); document.querySelectorAll(".ttab[data-bk]").forEach(function (x) { x.classList.toggle("active", x === b); }); rtr(); }); });
  document.querySelectorAll(".ttab[data-shz]").forEach(function (b) { b.addEventListener("click", function () { st.shz = b.getAttribute("data-shz"); document.querySelectorAll(".ttab[data-shz]").forEach(function (x) { x.classList.toggle("active", x === b); }); rsug(); }); });
  document.querySelectorAll(".ttab[data-nt]").forEach(function (b) { b.addEventListener("click", function () { st.nt = b.getAttribute("data-nt"); document.querySelectorAll(".ttab[data-nt]").forEach(function (x) { x.classList.toggle("active", x === b); }); rn(); }); });
  document.addEventListener("click", function (e) { var c = e.target.closest("[data-tk]"); if (c) { open(c.getAttribute("data-tk")); } });

  // ---------- init ----------
  ld(); lsug(); lmkt();
  setInterval(function () { ld(); lsug(); lmkt(); }, 5 * 60 * 1000);
})();
