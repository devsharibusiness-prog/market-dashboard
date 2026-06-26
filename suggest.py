#!/usr/bin/env python3
"""
MAXIMAL Stock Suggestion + Market Context Engine.

Writes TWO files:
  - suggestions.json : per-ticker scored recommendations with sub-scores,
                       confidence, triggers, backtest win-rate, sparklines,
                       sector-relative return, setup grade, earnings stats,
                       and a CRUDE keyword sentiment label.
  - market.json      : market-wide regime, sector leaders/laggards, VIX,
                       a Fear & Greed PROXY (not CNN's official index),
                       and a key S&P 500 level to watch.

Free stack only: yfinance + pandas. Runs in GitHub Actions, no paid APIs.
Regex-free. Newlines via chr(10), never literal backslash-n inside strings.
Per-ticker try/except so one bad ticker never crashes the whole run.

NOT FINANCIAL ADVICE. Transparent rule-based scoring + historical statistics
for personal research only. A high score or high backtest win-rate does NOT
predict the future.
"""
import json
import datetime
import traceback
import yfinance as yf
import pandas as pd

# ============================================================
# CONFIG  <-- EDIT YOUR WATCHLIST HERE
# ============================================================
WATCHLIST = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"]

SECTOR_ETFS = ["XLK", "XLE", "XLF", "XLV", "XLI",
               "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC"]

# Map yfinance .info sector strings -> SPDR sector ETF
SECTOR_TO_ETF = {
    "Technology": "XLK",
    "Communication Services": "XLC",
    "Financial Services": "XLF",
    "Financial": "XLF",
    "Healthcare": "XLV",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Basic Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
}

# Crude keyword sentiment lexicon (NOT AI - simple word counts)
BULLISH_WORDS = ["beat", "beats", "surge", "soar", "jump", "rally", "record",
                 "upgrade", "raises", "raised", "strong", "growth", "gains",
                 "outperform", "buy", "bullish", "tops", "wins", "profit",
                 "boost", "expands", "high", "rises", "rose", "approve"]
BEARISH_WORDS = ["miss", "misses", "plunge", "drop", "fall", "falls", "fell",
                 "slump", "downgrade", "cuts", "cut", "weak", "loss", "losses",
                 "underperform", "sell", "bearish", "lawsuit", "probe", "warns",
                 "warning", "decline", "slows", "layoff", "layoffs", "recall"]

# ============================================================
# HELPERS
# ============================================================
def round2(x):
    try:
        return round(float(x), 2)
    except Exception:
        return None

def round1(x):
    try:
        return round(float(x), 1)
    except Exception:
        return None

def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    val = 100 - (100 / (1 + rs.iloc[-1]))
    return float(val) if pd.notna(val) else None

def rsi_series(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def atr(hist, period=14):
    high = hist["High"]
    low = hist["Low"]
    close = hist["Close"]
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    val = tr.rolling(period).mean().iloc[-1]
    return float(val) if pd.notna(val) else None

def pct_return(series, days):
    if len(series) <= days:
        return None
    old = series.iloc[-days - 1]
    new = series.iloc[-1]
    return float((new - old) / old * 100) if old else None

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

# ============================================================
# SUB-SCORES (each normalized 0-100)
# ============================================================
def score_rsi(r):
    if r is None:
        return 50.0
    if 40 <= r <= 60:
        return 100.0
    if 30 <= r < 40:
        return 85.0
    if 60 < r <= 70:
        return 55.0
    if r < 30:
        return 65.0
    return 25.0  # overbought >70

def score_momentum(m1, m3):
    s = 50.0
    if m1 is not None:
        if m1 > 5:
            s += 25
        elif m1 > 0:
            s += 12
        elif m1 > -5:
            s -= 5
        else:
            s -= 20
    if m3 is not None:
        if m3 > 10:
            s += 25
        elif m3 > 0:
            s += 12
        else:
            s -= 15
    return clamp(s, 0, 100)

def score_volume(volume_ratio):
    if volume_ratio is None:
        return 50.0
    if volume_ratio >= 1.5:
        return 100.0
    if volume_ratio >= 1.2:
        return 80.0
    if volume_ratio >= 1.0:
        return 60.0
    if volume_ratio >= 0.8:
        return 45.0
    return 30.0

def score_fundamental(fund):
    s = 0.0
    cnt = 0
    pe = fund.get("pe")
    rg = fund.get("rev_growth")
    mg = fund.get("margin")
    roe = fund.get("roe")
    de = fund.get("debt_to_equity")
    if pe is not None and pe > 0:
        cnt += 1
        if pe < 15:
            s += 100
        elif pe < 25:
            s += 80
        elif pe < 40:
            s += 50
        else:
            s += 25
    if rg is not None:
        cnt += 1
        if rg > 20:
            s += 100
        elif rg > 10:
            s += 80
        elif rg > 0:
            s += 55
        else:
            s += 20
    if mg is not None:
        cnt += 1
        if mg > 20:
            s += 100
        elif mg > 10:
            s += 75
        elif mg > 0:
            s += 50
        else:
            s += 10
    if roe is not None:
        cnt += 1
        if roe > 20:
            s += 100
        elif roe > 10:
            s += 75
        elif roe > 0:
            s += 50
        else:
            s += 15
    if de is not None:
        cnt += 1
        if de < 50:
            s += 100
        elif de < 100:
            s += 70
        elif de < 200:
            s += 45
        else:
            s += 20
    if cnt == 0:
        return 50.0
    return clamp(s / cnt, 0, 100)

# ============================================================
# CONFIDENCE: how many sub-signals agree (point the same way)
# ============================================================
def compute_confidence(rsi_s, mom_s, fund_s, vol_s):
    subs = [rsi_s, mom_s, fund_s, vol_s]
    bullish = sum(1 for x in subs if x >= 60)
    bearish = sum(1 for x in subs if x <= 40)
    agree = max(bullish, bearish)
    # 4 aligned -> ~95, 3 -> ~78, 2 -> ~60, else ~45
    table = {4: 95.0, 3: 78.0, 2: 60.0, 1: 48.0, 0: 40.0}
    return table.get(agree, 50.0)

# ============================================================
# TRIGGER CONDITION TEXT
# ============================================================
def build_trigger(rsi_now, rsi_prev, price, ma50, ma200, volume_ratio, m1):
    if rsi_now is not None and rsi_prev is not None and rsi_prev < 40 <= rsi_now:
        return "RSI bouncing off " + str(int(round(rsi_prev)))
    if price is not None and ma50 is not None and price > ma50 and m1 is not None and m1 > 0:
        return "Reclaimed 50-day MA"
    if volume_ratio is not None and volume_ratio >= 1.4:
        return "Volume " + str(round1(volume_ratio)) + "x average"
    if price is not None and ma200 is not None and price > ma200:
        return "Holding above 200-day MA"
    if rsi_now is not None and rsi_now < 30:
        return "Oversold (RSI " + str(int(round(rsi_now))) + ")"
    if rsi_now is not None and rsi_now > 70:
        return "Overbought (RSI " + str(int(round(rsi_now))) + ")"
    return "Mixed - monitor for confirmation"

# ============================================================
# BACKTEST: historical frequency, NOT a prediction
# ============================================================
def backtest_setup(hist, horizon_days=5):
    """
    Over the available history, find days matching the CURRENT setup type
    and measure what fraction saw a positive return horizon_days later.
    Setup type chosen by current RSI + trend position.
    """
    try:
        close = hist["Close"].dropna()
        if len(close) < 220:
            return None, 0, "Insufficient history for backtest"
        r = rsi_series(close)
        ma200 = close.rolling(200).mean()
        ma50 = close.rolling(50).mean()
        cur_rsi = r.iloc[-1]
        cur_price = close.iloc[-1]
        cur_ma200 = ma200.iloc[-1]

        if pd.isna(cur_rsi) or pd.isna(cur_ma200):
            return None, 0, "Setup undefined"

        above_200 = cur_price > cur_ma200
        if cur_rsi < 35:
            cond_label = "RSI<35"
            cond = r < 35
        elif cur_rsi > 70:
            cond_label = "RSI>70"
            cond = r > 70
        elif cur_price > ma50.iloc[-1]:
            cond_label = "price>50MA"
            cond = close > ma50
        else:
            cond_label = "RSI 35-70"
            cond = (r >= 35) & (r <= 70)

        trend_label = "above 200MA" if above_200 else "below 200MA"
        if above_200:
            cond = cond & (close > ma200)
        else:
            cond = cond & (close <= ma200)

        future = close.shift(-horizon_days)
        fwd_ret = (future - close) / close
        mask = cond.fillna(False)
        # exclude last horizon_days (no future data)
        valid = mask & fwd_ret.notna()
        sample = int(valid.sum())
        if sample < 10:
            return None, sample, "Too few matches (" + str(sample) + ")"
        wins = int((fwd_ret[valid] > 0).sum())
        winrate = round1(wins / sample * 100)
        note = (str(cond_label) + " & " + trend_label + " -> up after "
                + str(horizon_days) + "d, " + str(sample) + " samples (~2y)")
        return winrate, sample, note
    except Exception:
        return None, 0, "Backtest error"

# ============================================================
# EARNINGS STATS
# ============================================================
def earnings_stats(t):
    eps_estimate = None
    streak = []
    avg_move = None
    try:
        info = t.info
        eps_estimate = info.get("epsForward") or info.get("forwardEps")
    except Exception:
        pass
    # beat/miss streak from earnings history
    try:
        eh = t.earnings_history
        if eh is not None and not eh.empty:
            rows = eh.tail(4)
            for _, row in rows.iterrows():
                est = row.get("epsEstimate")
                act = row.get("epsActual")
                if est is None or act is None or pd.isna(est) or pd.isna(act):
                    streak.append("n/a")
                elif act > est:
                    streak.append("beat")
                elif act < est:
                    streak.append("miss")
                else:
                    streak.append("in-line")
    except Exception:
        pass
    # average absolute post-earnings move from price reaction
    try:
        cal = t.get_earnings_dates(limit=8)
        if cal is not None and not cal.empty:
            hist = t.history(period="2y")
            closes = hist["Close"]
            moves = []
            for dt in cal.index:
                try:
                    d = pd.Timestamp(dt).tz_localize(None)
                    idx = closes.index.tz_localize(None) if closes.index.tz is not None else closes.index
                    pos = idx.searchsorted(d)
                    if 1 <= pos < len(closes) - 1:
                        before = closes.iloc[pos - 1]
                        after = closes.iloc[pos]
                        if before:
                            moves.append(abs((after - before) / before * 100))
                except Exception:
                    continue
            if moves:
                avg_move = round1(sum(moves) / len(moves))
    except Exception:
        pass
    return {
        "eps_estimate": round2(eps_estimate),
        "earnings_streak": streak,
        "avg_post_earnings_move_pct": avg_move,
    }

# ============================================================
# CRUDE KEYWORD SENTIMENT (NOT AI)
# ============================================================
def keyword_sentiment(t):
    headline = None
    label = "neutral"
    try:
        news = t.news
        if news and len(news) > 0:
            headline = news[0].get("title")
    except Exception:
        headline = None
    if not headline:
        return {"headline": None, "label": "neutral",
                "method": "crude keyword heuristic, NOT AI"}
    low = headline.lower()
    b = sum(1 for w in BULLISH_WORDS if w in low)
    s = sum(1 for w in BEARISH_WORDS if w in low)
    if b > s:
        label = "bullish"
    elif s > b:
        label = "bearish"
    return {"headline": headline, "label": label,
            "bullish_hits": b, "bearish_hits": s,
            "method": "crude keyword heuristic, NOT AI"}

# ============================================================
# SECTOR-RELATIVE RETURN
# ============================================================
def sector_etf_for(t, sector_cache):
    etf = "XLK"
    try:
        sec = t.info.get("sector")
        if sec and sec in SECTOR_TO_ETF:
            etf = SECTOR_TO_ETF[sec]
    except Exception:
        pass
    return etf

def etf_1m_return(etf, cache):
    if etf in cache:
        return cache[etf]
    val = None
    try:
        h = yf.Ticker(etf).history(period="3mo")
        val = pct_return(h["Close"], 21)
    except Exception:
        val = None
    cache[etf] = val
    return val

# ============================================================
# HORIZON + CONVICTION + SETUP GRADE
# ============================================================
def decide_horizon(tech):
    vola = tech.get("volatility") or 0
    m1 = tech.get("mom_1m") or 0
    rsi_v = tech.get("rsi") or 50
    price = tech.get("price")
    ma200 = tech.get("ma200")
    long_ok = (ma200 is not None and price is not None and price > ma200)
    if vola >= 3.0 and abs(m1) >= 5:
        return "intraday", "High volatility + strong short-term momentum"
    if 35 <= rsi_v <= 65 and m1 > 0:
        return "swing", "Recovering momentum in a tradeable range"
    if long_ok:
        return "long_term", "Established uptrend, suited to holding"
    return "swing", "Mixed signals - monitor on swing timeframe"

def conviction(total):
    if total >= 75:
        return "Strong", chr(0x1F7E2)   # green circle
    if total >= 55:
        return "Moderate", chr(0x1F7E1)  # yellow circle
    return "Weak", chr(0x26AA)           # white circle

def expected_window(horizon):
    return {"intraday": "Hours to 1-2 days",
            "swing": "1-6 weeks",
            "long_term": "6-18+ months"}.get(horizon, "Varies")

def setup_grade(rr, trend_aligned, vola):
    """A/B/C from R:R + trend alignment + volatility."""
    score = 0
    if rr is not None:
        if rr >= 2.5:
            score += 3
        elif rr >= 1.5:
            score += 2
        elif rr >= 1.0:
            score += 1
    if trend_aligned:
        score += 2
    if vola is not None and vola < 3.5:
        score += 1
    if score >= 5:
        return "A"
    if score >= 3:
        return "B"
    return "C"

# ============================================================
# PER-TICKER ANALYSIS
# ============================================================
def analyze(ticker, etf_cache):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="2y")
        if hist is None or hist.empty or len(hist) < 40:
            print("  [skip] " + ticker + ": insufficient history")
            return None

        close = hist["Close"].dropna()
        price = float(close.iloc[-1])

        # --- indicators ---
        r_series = rsi_series(close)
        r = float(r_series.iloc[-1]) if pd.notna(r_series.iloc[-1]) else None
        r_prev = float(r_series.iloc[-2]) if len(r_series) > 1 and pd.notna(r_series.iloc[-2]) else None
        ma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
        ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
        m1 = pct_return(close, 21)
        m3 = pct_return(close, 63)
        hi = float(close.max())
        lo = float(close.min())
        pos = (price - lo) / (hi - lo) * 100 if hi != lo else 50.0
        daily_ret = close.pct_change().dropna()
        vola = float(daily_ret.iloc[-20:].std() * 100) if len(daily_ret) >= 20 else None
        atr_val = atr(hist)

        # volume ratio
        vol = hist["Volume"]
        volume_ratio = None
        if len(vol) >= 20:
            recent = float(vol.iloc[-5:].mean())
            base = float(vol.iloc[-20:].mean())
            volume_ratio = round2(recent / base) if base else None

        # sparkline = last 5 closes
        sparkline = [round2(x) for x in close.iloc[-5:].tolist()]

        # sector relative
        etf = sector_etf_for(t, etf_cache)
        etf_ret = etf_1m_return(etf, etf_cache)
        sector_rel = round1(m1 - etf_ret) if (m1 is not None and etf_ret is not None) else None

        # --- fundamentals ---
        try:
            info = t.info
        except Exception:
            info = {}
        pe = info.get("trailingPE")
        rev_growth = info.get("revenueGrowth")
        margin = info.get("profitMargins")
        roe = info.get("returnOnEquity")
        de = info.get("debtToEquity")
        fund_raw = {
            "pe": round2(pe),
            "rev_growth": round1(rev_growth * 100) if rev_growth is not None else None,
            "margin": round1(margin * 100) if margin is not None else None,
            "roe": round1(roe * 100) if roe is not None else None,
            "debt_to_equity": round2(de),
        }

        # --- sub-scores (0-100) ---
        rsi_s = round1(score_rsi(r))
        mom_s = round1(score_momentum(m1, m3))
        vol_s = round1(score_volume(volume_ratio))
        fund_s = round1(score_fundamental(fund_raw))

        # weighted total (technical 60%, fundamental 40%)
        tech_avg = (rsi_s + mom_s + vol_s) / 3.0
        total = round1(tech_avg * 0.6 + fund_s * 0.4)

        # technical_score / fundamental_score on 0-50 for the existing modal
        technical_score = round1(tech_avg / 2.0)
        fundamental_score = round1(fund_s / 2.0)

        # confidence
        conf = round1(compute_confidence(rsi_s, mom_s, fund_s, vol_s))

        # trigger
        trigger = build_trigger(r, r_prev, price, ma50, ma200, volume_ratio, m1)

        # backtest
        winrate, sample, bt_note = backtest_setup(hist, 5)

        # earnings + sentiment
        earn = earnings_stats(t)
        sentiment = keyword_sentiment(t)

        # horizon + conviction
        tech_obj = {"rsi": round2(r), "ma50": round2(ma50), "ma200": round2(ma200),
                    "mom_1m": round1(m1), "mom_3m": round1(m3), "pos_52w": round1(pos),
                    "volatility": round2(vola), "price": round2(price)}
        horizon, hreason = decide_horizon(tech_obj)
        conv_label, conv_emoji = conviction(total)

        # trade setup grade + breakout
        rr = None
        if atr_val:
            entry = price
            stop = price - atr_val * 1.5
            target = price + atr_val * 3.0
            risk = entry - stop
            reward = target - entry
            rr = round2(reward / risk) if risk else None
        trend_aligned = (ma200 is not None and price > ma200)
        grade = setup_grade(rr, trend_aligned, vola)

        # breakout = recent 20-day swing high
        breakout_level = round2(float(close.iloc[-20:].max())) if len(close) >= 20 else None
        breakout_distance_pct = None
        if breakout_level and price:
            breakout_distance_pct = round1((breakout_level - price) / price * 100)

        # build notes for existing modal compatibility
        tech_notes = []
        if r is not None:
            tech_notes.append("RSI " + str(int(round(r))))
        if trend_aligned:
            tech_notes.append("Above 200MA")
        if m1 is not None:
            tech_notes.append("1M " + ("+" if m1 >= 0 else "") + str(round1(m1)) + "%")
        if volume_ratio is not None:
            tech_notes.append("Vol " + str(round1(volume_ratio)) + "x")
        fund_notes = []
        if fund_raw["pe"] is not None:
            fund_notes.append("P/E " + str(fund_raw["pe"]))
        if fund_raw["rev_growth"] is not None:
            fund_notes.append("Rev " + ("+" if fund_raw["rev_growth"] >= 0 else "") + str(fund_raw["rev_growth"]) + "%")
        if fund_raw["margin"] is not None:
            fund_notes.append("Margin " + str(fund_raw["margin"]) + "%")

        rec = {
            "ticker": ticker,
            "total_score": total,
            "technical_score": technical_score,
            "fundamental_score": fundamental_score,
            "rsi_score": rsi_s,
            "momentum_score": mom_s,
            "fundamental_subscore": fund_s,
            "volume_score": vol_s,
            "confidence_pct": conf,
            "horizon": horizon,
            "expected_window": expected_window(horizon),
            "horizon_reason": hreason,
            "conviction": conv_label,
            "conviction_emoji": conv_emoji,
            "trigger": trigger,
            "backtest_winrate": winrate,
            "backtest_sample": sample,
            "backtest_note": bt_note,
            "setup_grade": grade,
            "breakout_level": breakout_level,
            "breakout_distance_pct": breakout_distance_pct,
            "rr": rr,
            "sentiment": sentiment,
            "tech_notes": tech_notes,
            "fund_notes": fund_notes,
            "technicals": {
                "rsi": round2(r), "ma50": round2(ma50), "ma200": round2(ma200),
                "mom_1m": round1(m1), "mom_3m": round1(m3), "pos_52w": round1(pos),
                "volatility": round2(vola), "price": round2(price), "atr": round2(atr_val),
                "sparkline": sparkline, "volume_ratio": volume_ratio,
                "sector_rel": sector_rel, "sector_etf": etf,
            },
            "fundamentals": {
                "pe": fund_raw["pe"], "rev_growth": fund_raw["rev_growth"],
                "margin": fund_raw["margin"], "roe": fund_raw["roe"],
                "debt_to_equity": fund_raw["debt_to_equity"],
                "eps_estimate": earn["eps_estimate"],
                "earnings_streak": earn["earnings_streak"],
                "avg_post_earnings_move_pct": earn["avg_post_earnings_move_pct"],
            },
        }
        print("  [ok]   " + ticker + ": " + str(total) + "/100 " + conv_label
              + " conf " + str(conf) + "% grade " + grade
              + (" win " + str(winrate) + "%" if winrate is not None else ""))
        return rec
    except Exception as e:
        print("  [FAIL] " + ticker + ": " + str(e))
        traceback.print_exc()
        return None

# ============================================================
# MARKET CONTEXT (market.json)
# ============================================================
def build_market(etf_cache):
    market = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "regime": None, "regime_reason": None, "sectors": [],
        "top2_leading": [], "top2_lagging": [], "vix": None, "vix_label": None,
        "fear_greed_proxy": None, "fg_label": None, "fg_note": None,
        "key_spy_level": None,
    }

    # --- SPY trend + regime ---
    spy_mom = None
    spy_price = None
    try:
        spy = yf.Ticker("SPY").history(period="6mo")
        sc = spy["Close"].dropna()
        spy_price = float(sc.iloc[-1])
        ma50 = float(sc.rolling(50).mean().iloc[-1]) if len(sc) >= 50 else None
        slope = pct_return(sc, 20)
        spy_mom = slope
        dret = sc.pct_change().dropna()
        spy_vola = float(dret.iloc[-20:].std() * 100) if len(dret) >= 20 else 0.0

        if spy_vola >= 1.6:
            regime = "volatile"
            reason = "SPY 20d daily vol " + str(round1(spy_vola)) + "% (elevated)"
        elif slope is not None and abs(slope) >= 4:
            regime = "trend"
            reason = "SPY 20d move " + ("+" if slope >= 0 else "") + str(round1(slope)) + "% (directional)"
        else:
            regime = "range"
            reason = "SPY drifting, low directional momentum"
        market["regime"] = regime
        market["regime_reason"] = reason

        # key SPY level: recent 20-day swing high/low closest to price
        sh = float(sc.iloc[-20:].max())
        sl = float(sc.iloc[-20:].min())
        if abs(sh - spy_price) <= abs(spy_price - sl):
            level = sh
            kind = "resistance"
        else:
            level = sl
            kind = "support"
        dist = round1((level - spy_price) / spy_price * 100)
        market["key_spy_level"] = {
            "level": round2(level), "kind": kind,
            "spy_price": round2(spy_price), "distance_pct": dist,
        }
    except Exception:
        market["regime"] = "unknown"
        market["regime_reason"] = "SPY data unavailable"

    # --- sectors ---
    sectors = []
    for etf in SECTOR_ETFS:
        try:
            h = yf.Ticker(etf).history(period="3mo")
            c = h["Close"].dropna()
            d1 = pct_return(c, 1)
            d1m = pct_return(c, 21)
            sectors.append({"etf": etf, "ret_1d": round1(d1), "ret_1m": round1(d1m)})
        except Exception:
            sectors.append({"etf": etf, "ret_1d": None, "ret_1m": None})
    market["sectors"] = sectors
    ranked = [s for s in sectors if s["ret_1m"] is not None]
    ranked.sort(key=lambda x: x["ret_1m"], reverse=True)
    market["top2_leading"] = ranked[:2]
    market["top2_lagging"] = ranked[-2:][::-1] if len(ranked) >= 2 else []

    # --- VIX ---
    vix_val = None
    try:
        vx = yf.Ticker("^VIX").history(period="1mo")
        vix_val = float(vx["Close"].dropna().iloc[-1])
        market["vix"] = round2(vix_val)
        if vix_val < 14:
            market["vix_label"] = "low"
        elif vix_val < 20:
            market["vix_label"] = "normal"
        elif vix_val < 28:
            market["vix_label"] = "elevated"
        else:
            market["vix_label"] = "high"
    except Exception:
        market["vix_label"] = "unknown"

    # --- Fear & Greed PROXY (NOT CNN's official index) ---
    try:
        comp = []
        # VIX inverted -> calm = greedy
        if vix_val is not None:
            vix_component = clamp(100 - (vix_val - 10) * 4, 0, 100)
            comp.append(vix_component)
        # SPY momentum -> positive = greedy
        if spy_mom is not None:
            mom_component = clamp(50 + spy_mom * 5, 0, 100)
            comp.append(mom_component)
        # breadth: fraction of sectors positive on 1m
        pos = [s for s in sectors if s["ret_1m"] is not None and s["ret_1m"] > 0]
        tot = [s for s in sectors if s["ret_1m"] is not None]
        if tot:
            breadth = len(pos) / len(tot) * 100
            comp.append(breadth)
        if comp:
            fg = round(sum(comp) / len(comp))
            market["fear_greed_proxy"] = fg
            if fg < 25:
                lab = "Extreme Fear"
            elif fg < 45:
                lab = "Fear"
            elif fg < 55:
                lab = "Neutral"
            elif fg < 75:
                lab = "Greed"
            else:
                lab = "Extreme Greed"
            market["fg_label"] = lab
            market["fg_note"] = "PROXY (not CNN's official index): VIX + SPY momentum + sector breadth"
    except Exception:
        market["fear_greed_proxy"] = None
        market["fg_note"] = "PROXY unavailable"

    return market

# ============================================================
# MAIN
# ============================================================
def main():
    print("Analyzing " + str(len(WATCHLIST)) + " tickers (maximal engine)...")
    etf_cache = {}
    recs = []
    for tk in WATCHLIST:
        r = analyze(tk, etf_cache)
        if r:
            recs.append(r)

    recs.sort(key=lambda x: x["total_score"], reverse=True)
    buckets = {"intraday": [], "swing": [], "long_term": []}
    for r in recs:
        buckets[r["horizon"]].append(r)

    suggestions = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "suggestions": recs,
        "by_horizon": buckets,
        "top_picks": recs[:5],
        "disclaimer": "Not financial advice. Transparent rule-based scoring + "
                      "historical statistics for research only. Backtest win-rate "
                      "is a past frequency, NOT a prediction.",
    }
    with open("suggestions.json", "w") as f:
        json.dump(suggestions, f, indent=2)

    print("")
    print("Building market context (regime, sectors, VIX, F&G proxy)...")
    market = build_market(etf_cache)
    with open("market.json", "w") as f:
        json.dump(market, f, indent=2)

    print("")
    print("Wrote suggestions.json with " + str(len(recs)) + " scored stocks.")
    print("Wrote market.json (regime=" + str(market.get("regime"))
          + ", VIX=" + str(market.get("vix"))
          + ", F&G proxy=" + str(market.get("fear_greed_proxy")) + ").")

if __name__ == "__main__":
    main()
