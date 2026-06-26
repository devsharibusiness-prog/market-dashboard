#!/usr/bin/env python3
"""
suggest.py - direction-aware engine (long for uptrend, short for downtrend).
Writes suggestions.json, market.json, and appends signal_history.json.
Free stack: yfinance + pandas. Regex-free. No backslash-n in strings.
NOT financial advice. Shorting carries higher risk.
"""
import json
import os
import datetime
import traceback
import yfinance as yf
import pandas as pd

# ============================================================
# CONFIG  <-- KEEP WATCHLIST IDENTICAL TO fetch_data.py
# ============================================================
WATCHLIST = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"]
ACCOUNT_SIZE = 10000.0
RISK_PCT = 1.0

SECTOR_ETFS = ["XLK", "XLE", "XLF", "XLV", "XLI",
               "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC"]
SECTOR_TO_ETF = {
    "Technology": "XLK", "Communication Services": "XLC",
    "Financial Services": "XLF", "Financial": "XLF",
    "Healthcare": "XLV", "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP", "Energy": "XLE",
    "Industrials": "XLI", "Basic Materials": "XLB",
    "Utilities": "XLU", "Real Estate": "XLRE",
}
BULLISH_WORDS = ["beat", "beats", "surge", "soar", "jump", "rally", "record",
                 "upgrade", "raises", "strong", "growth", "gains", "outperform",
                 "buy", "bullish", "tops", "wins", "profit", "boost", "high", "approve"]
BEARISH_WORDS = ["miss", "misses", "plunge", "drop", "fall", "fell", "slump",
                 "downgrade", "cuts", "weak", "loss", "losses", "underperform",
                 "sell", "bearish", "lawsuit", "probe", "warns", "decline", "layoff", "recall"]

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

def rsi_series(series, period=14):
    d = series.diff()
    g = d.clip(lower=0).rolling(period).mean()
    l = -d.clip(upper=0).rolling(period).mean()
    rs = g / l
    return 100 - (100 / (1 + rs))

def atr(hist, period=14):
    h = hist["High"]
    lo = hist["Low"]
    c = hist["Close"]
    p = c.shift(1)
    tr = pd.concat([(h - lo), (h - p).abs(), (lo - p).abs()], axis=1).max(axis=1)
    v = tr.rolling(period).mean().iloc[-1]
    return round2(v) if pd.notna(v) else None

def pct_return(series, days):
    if len(series) <= days:
        return None
    o = series.iloc[-days - 1]
    nw = series.iloc[-1]
    return float((nw - o) / o * 100) if o else None

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

# ============================================================
# SUB-SCORES (0-100)
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
    return 25.0

def score_momentum(m1, m3):
    s = 50.0
    if m1 is not None:
        s += 25 if m1 > 5 else 12 if m1 > 0 else -5 if m1 > -5 else -20
    if m3 is not None:
        s += 25 if m3 > 10 else 12 if m3 > 0 else -15
    return clamp(s, 0, 100)

def score_volume(vr):
    if vr is None:
        return 50.0
    return 100.0 if vr >= 1.5 else 80.0 if vr >= 1.2 else 60.0 if vr >= 1.0 else 45.0 if vr >= 0.8 else 30.0

def score_fundamental(f):
    s = 0.0
    cnt = 0
    pe = f.get("pe")
    rg = f.get("rev_growth")
    mg = f.get("margin")
    roe = f.get("roe")
    de = f.get("debt_to_equity")
    if pe is not None and pe > 0:
        cnt += 1
        s += 100 if pe < 15 else 80 if pe < 25 else 50 if pe < 40 else 25
    if rg is not None:
        cnt += 1
        s += 100 if rg > 20 else 80 if rg > 10 else 55 if rg > 0 else 20
    if mg is not None:
        cnt += 1
        s += 100 if mg > 20 else 75 if mg > 10 else 50 if mg > 0 else 10
    if roe is not None:
        cnt += 1
        s += 100 if roe > 20 else 75 if roe > 10 else 50 if roe > 0 else 15
    if de is not None:
        cnt += 1
        s += 100 if de < 50 else 70 if de < 100 else 45 if de < 200 else 20
    if cnt == 0:
        return 50.0
    return clamp(s / cnt, 0, 100)

def compute_confidence(a, b, c, d):
    subs = [a, b, c, d]
    bull = sum(1 for x in subs if x >= 60)
    bear = sum(1 for x in subs if x <= 40)
    agree = max(bull, bear)
    return {4: 95.0, 3: 78.0, 2: 60.0, 1: 48.0, 0: 40.0}.get(agree, 50.0)

def build_trigger(rn, rp, price, ma50, ma200, vr, m1):
    if rn is not None and rp is not None and rp < 40 <= rn:
        return "RSI bouncing off " + str(int(round(rp)))
    if price is not None and ma50 is not None and price > ma50 and m1 is not None and m1 > 0:
        return "Reclaimed 50-day MA"
    if vr is not None and vr >= 1.4:
        return "Volume " + str(round1(vr)) + "x average"
    if price is not None and ma200 is not None and price > ma200:
        return "Holding above 200-day MA"
    if rn is not None and rn < 30:
        return "Oversold (RSI " + str(int(round(rn))) + ")"
    if rn is not None and rn > 70:
        return "Overbought (RSI " + str(int(round(rn))) + ")"
    return "Mixed - monitor for confirmation"

# ============================================================
# BACKTEST + EXPECTED VALUE
# ============================================================
def backtest_setup(hist, horizon_days=5):
    try:
        close = hist["Close"].dropna()
        if len(close) < 220:
            return {"winrate": None, "sample": 0, "note": "Insufficient history",
                    "avg_win": None, "avg_loss": None, "ev_pct": None, "low_sample": True}
        r = rsi_series(close)
        ma200 = close.rolling(200).mean()
        ma50 = close.rolling(50).mean()
        cr = r.iloc[-1]
        cp = close.iloc[-1]
        cm = ma200.iloc[-1]
        if pd.isna(cr) or pd.isna(cm):
            return {"winrate": None, "sample": 0, "note": "Setup undefined",
                    "avg_win": None, "avg_loss": None, "ev_pct": None, "low_sample": True}
        above = cp > cm
        if cr < 35:
            label = "RSI<35"
            cond = r < 35
        elif cr > 70:
            label = "RSI>70"
            cond = r > 70
        elif cp > ma50.iloc[-1]:
            label = "price>50MA"
            cond = close > ma50
        else:
            label = "RSI 35-70"
            cond = (r >= 35) & (r <= 70)
        tl = "above 200MA" if above else "below 200MA"
        cond = cond & (close > ma200) if above else cond & (close <= ma200)
        fwd = (close.shift(-horizon_days) - close) / close * 100
        valid = cond.fillna(False) & fwd.notna()
        sample = int(valid.sum())
        if sample < 10:
            return {"winrate": None, "sample": sample, "note": "Too few matches",
                    "avg_win": None, "avg_loss": None, "ev_pct": None, "low_sample": True}
        rets = fwd[valid]
        wins = rets[rets > 0]
        losses = rets[rets <= 0]
        wr = round1(len(wins) / sample * 100)
        avg_win = round2(wins.mean()) if len(wins) else 0.0
        avg_loss = round2(losses.mean()) if len(losses) else 0.0
        pw = len(wins) / sample
        pl = len(losses) / sample
        ev = round2(pw * (avg_win or 0) + pl * (avg_loss or 0))
        note = label + " & " + tl + " -> " + str(horizon_days) + "d fwd, " + str(sample) + " samples"
        return {"winrate": wr, "sample": sample, "note": note, "avg_win": avg_win,
                "avg_loss": avg_loss, "ev_pct": ev, "low_sample": sample < 30}
    except Exception:
        return {"winrate": None, "sample": 0, "note": "Backtest error",
                "avg_win": None, "avg_loss": None, "ev_pct": None, "low_sample": True}

# ============================================================
# SWING LEVELS
# ============================================================
def swing_levels(close, lookback=20):
    if len(close) < lookback:
        return None, None
    window = close.iloc[-lookback:]
    return round2(float(window.max())), round2(float(window.min()))

# ============================================================
# DIRECTION-AWARE TRADE BUCKETS (long uptrend / short downtrend)
# ============================================================
def build_trade_buckets(price, atr_val, resistance, support, direction):
    if not price or not atr_val:
        return {}

    def long_setup(stop_ref, target_ref, atr_stop, atr_target):
        stop = stop_ref if (stop_ref and stop_ref < price) else round2(price - atr_stop * atr_val)
        target = target_ref if (target_ref and target_ref > price) else round2(price + atr_target * atr_val)
        risk = price - stop
        reward = target - price
        rr = round2(reward / risk) if risk and risk > 0 else None
        return {"direction": "long", "action": "BUY", "exit_action": "SELL",
                "entry": round2(price), "stop": stop, "target": target, "rr": rr}

    def short_setup(stop_ref, target_ref, atr_stop, atr_target):
        stop = stop_ref if (stop_ref and stop_ref > price) else round2(price + atr_stop * atr_val)
        target = target_ref if (target_ref and target_ref < price) else round2(price - atr_target * atr_val)
        risk = stop - price
        reward = price - target
        rr = round2(reward / risk) if risk and risk > 0 else None
        return {"direction": "short", "action": "SELL/SHORT", "exit_action": "BUY/COVER",
                "entry": round2(price), "stop": stop, "target": target, "rr": rr}

    if direction == "short":
        return {
            "intraday": short_setup(round2(price + 1.0 * atr_val), round2(price - 1.5 * atr_val), 1.0, 1.5),
            "swing": short_setup(resistance, support, 1.5, 3.0),
            "long_term": short_setup(round2(price + 3.0 * atr_val), round2(price - 8.0 * atr_val), 3.0, 8.0),
        }
    return {
        "intraday": long_setup(round2(price - 1.0 * atr_val), round2(price + 1.5 * atr_val), 1.0, 1.5),
        "swing": long_setup(support, resistance, 1.5, 3.0),
        "long_term": long_setup(support, round2(price + 8.0 * atr_val), 3.0, 8.0),
    }

# ============================================================
# POSITION SIZING (direction-aware)
# ============================================================
def position_size(price, stop, direction):
    if not price or not stop:
        return None
    risk_per_share = (price - stop) if direction == "long" else (stop - price)
    if risk_per_share <= 0:
        return None
    dollar_risk = ACCOUNT_SIZE * (RISK_PCT / 100.0)
    shares = int(dollar_risk / risk_per_share)
    return {"shares": shares, "dollar_risk": round2(dollar_risk),
            "position_value": round2(shares * price),
            "risk_per_share": round2(risk_per_share), "direction": direction}

# ============================================================
# EARNINGS / SENTIMENT / SECTOR
# ============================================================
def earnings_stats(t):
    eps = None
    streak = []
    avg = None
    try:
        eps = t.info.get("epsForward") or t.info.get("forwardEps")
    except Exception:
        pass
    try:
        eh = t.earnings_history
        if eh is not None and not eh.empty:
            for _, row in eh.tail(4).iterrows():
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
    try:
        cal = t.get_earnings_dates(limit=8)
        if cal is not None and not cal.empty:
            h = t.history(period="2y")
            closes = h["Close"]
            idx = closes.index.tz_localize(None) if closes.index.tz is not None else closes.index
            moves = []
            for dt in cal.index:
                try:
                    d = pd.Timestamp(dt).tz_localize(None)
                    pos = idx.searchsorted(d)
                    if 1 <= pos < len(closes) - 1:
                        before = closes.iloc[pos - 1]
                        after = closes.iloc[pos]
                        if before:
                            moves.append(abs((after - before) / before * 100))
                except Exception:
                    continue
            if moves:
                avg = round1(sum(moves) / len(moves))
    except Exception:
        pass
    return {"eps_estimate": round2(eps), "earnings_streak": streak,
            "avg_post_earnings_move_pct": avg}

def keyword_sentiment(t):
    headline = None
    try:
        news = t.news
        if news and len(news) > 0:
            headline = news[0].get("title")
    except Exception:
        headline = None
    if not headline:
        return {"headline": None, "label": "neutral", "method": "crude keyword heuristic, NOT AI"}
    low = headline.lower()
    b = sum(1 for w in BULLISH_WORDS if w in low)
    s = sum(1 for w in BEARISH_WORDS if w in low)
    label = "bullish" if b > s else "bearish" if s > b else "neutral"
    return {"headline": headline, "label": label, "bullish_hits": b, "bearish_hits": s,
            "method": "crude keyword heuristic, NOT AI"}

def get_sector(t):
    sec = None
    try:
        sec = t.info.get("sector")
    except Exception:
        sec = None
    etf = SECTOR_TO_ETF.get(sec, "XLK") if sec else "XLK"
    return (sec or "Unknown"), etf

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
# HORIZON / CONVICTION / GRADE
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
        return "Strong", chr(0x1F7E2)
    if total >= 55:
        return "Moderate", chr(0x1F7E1)
    return "Weak", chr(0x26AA)

def expected_window(h):
    return {"intraday": "Hours to 1-2 days", "swing": "1-6 weeks",
            "long_term": "6-18+ months"}.get(h, "Varies")

def setup_grade(rr, trend_aligned, vola):
    sc = 0
    if rr is not None:
        sc += 3 if rr >= 2.5 else 2 if rr >= 1.5 else 1 if rr >= 1.0 else 0
    if trend_aligned:
        sc += 2
    if vola is not None and vola < 3.5:
        sc += 1
    return "A" if sc >= 5 else "B" if sc >= 3 else "C"

# ============================================================
# PER-TICKER
# ============================================================
def analyze(ticker, etf_cache, spy_1m, spy_3m):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="2y")
        if hist is None or hist.empty or len(hist) < 40:
            print("  [skip] " + ticker + ": insufficient history")
            return None
        close = hist["Close"].dropna()
        price = float(close.iloc[-1])
        rs = rsi_series(close)
        r = float(rs.iloc[-1]) if pd.notna(rs.iloc[-1]) else None
        rp = float(rs.iloc[-2]) if len(rs) > 1 and pd.notna(rs.iloc[-2]) else None
        ma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
        ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
        m1 = pct_return(close, 21)
        m3 = pct_return(close, 63)
        hi = float(close.max())
        lo = float(close.min())
        pos = (price - lo) / (hi - lo) * 100 if hi != lo else 50.0
        dret = close.pct_change().dropna()
        vola = float(dret.iloc[-20:].std() * 100) if len(dret) >= 20 else None
        atr_val = atr(hist)
        vol = hist["Volume"]
        vr = None
        if len(vol) >= 20:
            recent = float(vol.iloc[-5:].mean())
            base = float(vol.iloc[-20:].mean())
            vr = round2(recent / base) if base else None
        sparkline = [round2(x) for x in close.iloc[-5:].tolist()]
        sector_name, etf = get_sector(t)
        etf_ret = etf_1m_return(etf, etf_cache)
        sector_rel = round1(m1 - etf_ret) if (m1 is not None and etf_ret is not None) else None
        rs_spy_1m = round1(m1 - spy_1m) if (m1 is not None and spy_1m is not None) else None
        rs_spy_3m = round1(m3 - spy_3m) if (m3 is not None and spy_3m is not None) else None
        trend = "neutral"
        if ma200 is not None:
            trend = "uptrend" if price > ma200 else "downtrend"
        trend_aligned = (ma200 is not None and price > ma200)

        try:
            info = t.info
        except Exception:
            info = {}
        f_raw = {
            "pe": round2(info.get("trailingPE")),
            "rev_growth": round1(info.get("revenueGrowth") * 100) if info.get("revenueGrowth") is not None else None,
            "margin": round1(info.get("profitMargins") * 100) if info.get("profitMargins") is not None else None,
            "roe": round1(info.get("returnOnEquity") * 100) if info.get("returnOnEquity") is not None else None,
            "debt_to_equity": round2(info.get("debtToEquity")),
        }
        rsi_s = round1(score_rsi(r))
        mom_s = round1(score_momentum(m1, m3))
        vol_s = round1(score_volume(vr))
        fund_s = round1(score_fundamental(f_raw))
        tech_avg = (rsi_s + mom_s + vol_s) / 3.0
        total = round1(tech_avg * 0.6 + fund_s * 0.4)
        technical_score = round1(tech_avg / 2.0)
        fundamental_score = round1(fund_s / 2.0)
        conf = round1(compute_confidence(rsi_s, mom_s, fund_s, vol_s))
        trigger = build_trigger(r, rp, price, ma50, ma200, vr, m1)
        bt = backtest_setup(hist, 5)
        earn = earnings_stats(t)
        sentiment = keyword_sentiment(t)

        resistance, support = swing_levels(close, 20)
        trade_direction = "short" if trend == "downtrend" else "long"
        buckets = build_trade_buckets(price, atr_val, resistance, support, trade_direction)
        swing = buckets.get("swing", {})
        swing_rr = swing.get("rr")
        swing_stop = swing.get("stop")
        possize = position_size(price, swing_stop, trade_direction)
        grade = setup_grade(swing_rr, trend_aligned, vola)
        breakout_level = resistance
        breakout_distance_pct = round1((resistance - price) / price * 100) if (resistance and price) else None

        tech_obj = {"rsi": round2(r), "ma200": round2(ma200), "mom_1m": round1(m1),
                    "volatility": round2(vola), "price": round2(price)}
        horizon, hreason = decide_horizon(tech_obj)
        conv_label, conv_emoji = conviction(total)

        tech_notes = []
        if r is not None:
            tech_notes.append("RSI " + str(int(round(r))))
        tech_notes.append(trend.capitalize())
        if m1 is not None:
            tech_notes.append("1M " + ("+" if m1 >= 0 else "") + str(round1(m1)) + "%")
        if vr is not None:
            tech_notes.append("RelVol " + str(round1(vr)) + "x (5d/20d)")
        fund_notes = []
        if f_raw["pe"] is not None:
            fund_notes.append("P/E " + str(f_raw["pe"]))
        if f_raw["rev_growth"] is not None:
            fund_notes.append("Rev " + ("+" if f_raw["rev_growth"] >= 0 else "") + str(f_raw["rev_growth"]) + "%")

        rec = {
            "ticker": ticker, "total_score": total, "score_formula": "60% technical + 40% fundamental",
            "technical_score": technical_score, "fundamental_score": fundamental_score,
            "rsi_score": rsi_s, "momentum_score": mom_s,
            "fundamental_subscore": fund_s, "volume_score": vol_s,
            "confidence_pct": conf, "horizon": horizon,
            "expected_window": expected_window(horizon), "horizon_reason": hreason,
            "conviction": conv_label, "conviction_emoji": conv_emoji,
            "trigger": trigger, "trend": trend, "trend_aligned": trend_aligned,
            "trade_direction": trade_direction,
            "backtest_winrate": bt["winrate"], "backtest_sample": bt["sample"],
            "backtest_note": bt["note"], "backtest_low_sample": bt["low_sample"],
            "avg_win_pct": bt["avg_win"], "avg_loss_pct": bt["avg_loss"], "ev_pct": bt["ev_pct"],
            "setup_grade": grade, "breakout_level": breakout_level,
            "breakout_distance_pct": breakout_distance_pct, "rr": swing_rr,
            "position_sizing": possize, "sentiment": sentiment,
            "relative_strength_1m": rs_spy_1m, "relative_strength_3m": rs_spy_3m,
            "tech_notes": tech_notes, "fund_notes": fund_notes,
            "technicals": {
                "rsi": round2(r), "ma50": round2(ma50), "ma200": round2(ma200),
                "mom_1m": round1(m1), "mom_3m": round1(m3), "pos_52w": round1(pos),
                "pos_52w_text": str(int(round(pos))) + "% of 52w range",
                "volatility": round2(vola), "price": round2(price), "atr": round2(atr_val),
                "sparkline": sparkline, "volume_ratio": vr,
                "volume_desc": "Relative volume = 5-day avg / 20-day avg",
                "sector_rel": sector_rel, "sector_etf": etf, "sector_name": sector_name,
                "support": support, "resistance": resistance,
                "rs_spy_1m": rs_spy_1m, "rs_spy_3m": rs_spy_3m,
            },
            "fundamentals": {
                "pe": f_raw["pe"], "rev_growth": f_raw["rev_growth"], "margin": f_raw["margin"],
                "roe": f_raw["roe"], "debt_to_equity": f_raw["debt_to_equity"],
                "sector": sector_name, "eps_estimate": earn["eps_estimate"],
                "earnings_streak": earn["earnings_streak"],
                "avg_post_earnings_move_pct": earn["avg_post_earnings_move_pct"],
            },
        }
        print("  [ok]   " + ticker + ": " + str(total) + "/100 " + conv_label
              + " grade " + grade + " RR " + str(swing_rr) + " " + trend
              + " (" + trade_direction + ")"
              + (" EV " + str(bt["ev_pct"]) + "%" if bt["ev_pct"] is not None else ""))
        return rec
    except Exception as e:
        print("  [FAIL] " + ticker + ": " + str(e))
        traceback.print_exc()
        return None

# ============================================================
# CONCENTRATION RISK
# ============================================================
def concentration_flags(recs, top_n=5):
    top = recs[:top_n]
    flags = []
    sectors = {}
    for r in top:
        s = r["fundamentals"].get("sector") or "Unknown"
        sectors[s] = sectors.get(s, 0) + 1
    for s, c in sectors.items():
        if c >= 3 and s != "Unknown":
            flags.append(str(c) + " of top " + str(len(top)) + " picks are in " + s + " - concentration risk")
    return flags

# ============================================================
# MARKET (VIX Sentiment)
# ============================================================
def build_market(etf_cache, spy_1m):
    mkt = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "regime": None, "regime_reason": None, "sectors": [],
        "top2_leading": [], "top2_lagging": [], "vix": None, "vix_label": None,
        "vix_sentiment": None, "vix_sentiment_label": None, "vix_sentiment_inputs": None,
        "key_spy_level": None,
    }
    spy_mom = spy_1m
    try:
        spy = yf.Ticker("SPY").history(period="6mo")
        sc = spy["Close"].dropna()
        spy_price = float(sc.iloc[-1])
        slope = pct_return(sc, 20)
        dret = sc.pct_change().dropna()
        spy_vola = float(dret.iloc[-20:].std() * 100) if len(dret) >= 20 else 0.0
        if spy_vola >= 1.6:
            mkt["regime"] = "volatile"
            mkt["regime_reason"] = "SPY 20d daily vol " + str(round1(spy_vola)) + "% (elevated)"
        elif slope is not None and abs(slope) >= 4:
            mkt["regime"] = "trend"
            mkt["regime_reason"] = "SPY 20d move " + ("+" if slope >= 0 else "") + str(round1(slope)) + "%"
        else:
            mkt["regime"] = "range"
            mkt["regime_reason"] = "SPY drifting, low directional momentum"
        sh = float(sc.iloc[-20:].max())
        sl = float(sc.iloc[-20:].min())
        if abs(sh - spy_price) <= abs(spy_price - sl):
            level = sh
            kind = "resistance"
        else:
            level = sl
            kind = "support"
        mkt["key_spy_level"] = {"level": round2(level), "kind": kind, "spy_price": round2(spy_price),
                                "distance_pct": round1((level - spy_price) / spy_price * 100)}
    except Exception:
        mkt["regime"] = "unknown"
        mkt["regime_reason"] = "SPY data unavailable"

    sectors = []
    for etf in SECTOR_ETFS:
        try:
            h = yf.Ticker(etf).history(period="3mo")
            c = h["Close"].dropna()
            sectors.append({"etf": etf, "ret_1d": round1(pct_return(c, 1)), "ret_1m": round1(pct_return(c, 21))})
        except Exception:
            sectors.append({"etf": etf, "ret_1d": None, "ret_1m": None})
    mkt["sectors"] = sectors
    ranked = [s for s in sectors if s["ret_1m"] is not None]
    ranked.sort(key=lambda x: x["ret_1m"], reverse=True)
    mkt["top2_leading"] = ranked[:2]
    mkt["top2_lagging"] = ranked[-2:][::-1] if len(ranked) >= 2 else []

    vix_val = None
    try:
        vx = yf.Ticker("^VIX").history(period="1mo")
        vix_val = float(vx["Close"].dropna().iloc[-1])
        mkt["vix"] = round2(vix_val)
        mkt["vix_label"] = "low" if vix_val < 14 else "normal" if vix_val < 20 else "elevated" if vix_val < 28 else "high"
        vs = clamp(100 - (vix_val - 10) * 4, 0, 100)
        mkt["vix_sentiment"] = round(vs)
        mkt["vix_sentiment_label"] = ("Extreme Fear" if vs < 25 else "Fear" if vs < 45
                                      else "Neutral" if vs < 55 else "Calm" if vs < 75 else "Complacent")
        mkt["vix_sentiment_inputs"] = "Derived from VIX only (inverted). Not CNN's Fear&Greed (which adds put/call, breadth, junk-bond demand)."
    except Exception:
        mkt["vix_label"] = "unknown"
    return mkt

# ============================================================
# SIGNAL HISTORY LOGGING
# ============================================================
def log_history(recs):
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    entry = {"date": today, "signals": [{"ticker": r["ticker"], "total_score": r["total_score"],
             "conviction": r["conviction"], "price": r["technicals"]["price"],
             "horizon": r["horizon"], "direction": r["trade_direction"]} for r in recs]}
    hist = []
    if os.path.exists("signal_history.json"):
        try:
            with open("signal_history.json", "r") as f:
                hist = json.load(f)
        except Exception:
            hist = []
    hist = [h for h in hist if h.get("date") != today]
    hist.append(entry)
    hist = hist[-180:]
    with open("signal_history.json", "w") as f:
        json.dump(hist, f, indent=2)
    print("Logged " + str(len(recs)) + " signals to signal_history.json (" + str(len(hist)) + " days tracked).")

# ============================================================
# MAIN
# ============================================================
def main():
    print("Analyzing " + str(len(WATCHLIST)) + " tickers (direction-aware engine)...")
    etf_cache = {}
    spy_1m = spy_3m = None
    try:
        spyh = yf.Ticker("SPY").history(period="6mo")["Close"]
        spy_1m = pct_return(spyh, 21)
        spy_3m = pct_return(spyh, 63)
    except Exception:
        pass

    recs = []
    for tk in WATCHLIST:
        r = analyze(tk, etf_cache, spy_1m, spy_3m)
        if r:
            recs.append(r)
    recs.sort(key=lambda x: x["total_score"], reverse=True)
    buckets = {"intraday": [], "swing": [], "long_term": []}
    for r in recs:
        buckets[r["horizon"]].append(r)

    suggestions = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "suggestions": recs, "by_horizon": buckets, "top_picks": recs[:5],
        "concentration_flags": concentration_flags(recs, 5),
        "account_size": ACCOUNT_SIZE, "risk_pct": RISK_PCT,
        "disclaimer": "Not financial advice. Rule-based stats only. Backtest/EV = past frequency, NOT a prediction. Shorting carries higher risk.",
    }
    with open("suggestions.json", "w") as f:
        json.dump(suggestions, f, indent=2)

    print("")
    print("Building market context (VIX Sentiment)...")
    market = build_market(etf_cache, spy_1m)
    with open("market.json", "w") as f:
        json.dump(market, f, indent=2)

    log_history(recs)

    print("")
    print("Wrote suggestions.json (" + str(len(recs)) + " stocks), market.json, signal_history.json.")
    print("regime=" + str(market.get("regime")) + " VIX=" + str(market.get("vix"))
          + " VIX-Sentiment=" + str(market.get("vix_sentiment")))

if __name__ == "__main__":
    main()
