#!/usr/bin/env python3
"""
Stock Suggestion Engine.
Scores each watchlist stock on TECHNICALS + FUNDAMENTALS, assigns a
time horizon (intraday / swing / long_term) and a conviction level.
Writes suggestions.json for the dashboard.

NOT financial advice. Transparent rule-based scoring for research only.
"""
import json, datetime, traceback
import yfinance as yf
import pandas as pd

# ---- CONFIG (match your fetch_data.py watchlist) ----
WATCHLIST = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"]   # <-- your tickers
# -----------------------------------------------------

def round2(x):
    try: return round(float(x), 2)
    except Exception: return None

# ---------- indicators ----------
def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    val = 100 - (100 / (1 + rs.iloc[-1]))
    return float(val) if pd.notna(val) else None

def pct_return(series, days):
    if len(series) <= days: return None
    old = series.iloc[-days-1]; new = series.iloc[-1]
    return float((new - old) / old * 100) if old else None

# ---------- TECHNICAL SCORE (0-50) ----------
def technical_score(hist):
    notes = []
    score = 0.0
    close = hist["Close"]
    price = float(close.iloc[-1])

    # RSI (0-12)
    r = rsi(close)
    if r is not None:
        if 40 <= r <= 60:      score += 12; notes.append(f"RSI {r:.0f} healthy")
        elif 30 <= r < 40:     score += 10; notes.append(f"RSI {r:.0f} recovering")
        elif 60 < r <= 70:     score += 6;  notes.append(f"RSI {r:.0f} strong")
        elif r < 30:           score += 7;  notes.append(f"RSI {r:.0f} oversold")
        else:                  score += 2;  notes.append(f"RSI {r:.0f} overbought")

    # Trend vs 50 & 200 MA (0-14)
    ma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
    ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
    if ma50 and ma200:
        if price > ma50 > ma200:   score += 14; notes.append("Strong uptrend (>50>200MA)")
        elif price > ma200:        score += 9;  notes.append("Above 200MA")
        elif price > ma50:         score += 6;  notes.append("Above 50MA")
        else:                      score += 1;  notes.append("Below key MAs")

    # Momentum 1M / 3M (0-12)
    m1 = pct_return(close, 21); m3 = pct_return(close, 63)
    if m1 is not None:
        if m1 > 5:    score += 6; notes.append(f"1M +{m1:.1f}%")
        elif m1 > 0:  score += 4
        elif m1 > -5: score += 2
    if m3 is not None:
        if m3 > 10:   score += 6; notes.append(f"3M +{m3:.1f}%")
        elif m3 > 0:  score += 4

    # 52-week position (0-6) - prefer mid-range
    hi = float(close.max()); lo = float(close.min())
    pos = (price - lo) / (hi - lo) * 100 if hi != lo else 50
    if 30 <= pos <= 75:   score += 6; notes.append(f"{pos:.0f}% of 52w range")
    elif pos < 30:        score += 4; notes.append(f"Near 52w low ({pos:.0f}%)")
    else:                 score += 2; notes.append(f"Near 52w high ({pos:.0f}%)")

    # Volume trend (0-6)
    vol = hist["Volume"]
    if len(vol) >= 20:
        recent = float(vol.iloc[-5:].mean()); base = float(vol.iloc[-20:].mean())
        if base and recent > base * 1.2: score += 6; notes.append("Rising volume")
        elif base and recent > base:     score += 3

    # volatility helper for horizon decision
    daily_ret = close.pct_change().dropna()
    vola = float(daily_ret.iloc[-20:].std() * 100) if len(daily_ret) >= 20 else None

    return round(min(score, 50), 1), notes, {
        "rsi": round2(r), "ma50": round2(ma50), "ma200": round2(ma200),
        "mom_1m": round2(m1), "mom_3m": round2(m3),
        "pos_52w": round2(pos), "volatility": round2(vola), "price": round2(price)
    }

# ---------- FUNDAMENTAL SCORE (0-50) ----------
def fundamental_score(t):
    notes = []
    score = 0.0
    data = {}
    try:
        info = t.info
    except Exception:
        info = {}

    pe = info.get("trailingPE")
    rev_growth = info.get("revenueGrowth")
    margin = info.get("profitMargins")
    roe = info.get("returnOnEquity")
    de = info.get("debtToEquity")

    # P/E (0-10)
    if pe is not None and pe > 0:
        if pe < 15:    score += 10; notes.append(f"P/E {pe:.0f} (cheap)")
        elif pe < 25:  score += 8;  notes.append(f"P/E {pe:.0f} (fair)")
        elif pe < 40:  score += 5;  notes.append(f"P/E {pe:.0f} (rich)")
        else:          score += 2;  notes.append(f"P/E {pe:.0f} (expensive)")
    else:
        score += 3  # neutral when unknown/negative

    # Revenue growth (0-12)
    if rev_growth is not None:
        g = rev_growth * 100
        if g > 20:    score += 12; notes.append(f"Rev growth +{g:.0f}%")
        elif g > 10:  score += 9;  notes.append(f"Rev growth +{g:.0f}%")
        elif g > 0:   score += 5
        else:         score += 1;  notes.append(f"Rev shrinking {g:.0f}%")
    else:
        score += 4

    # Profit margin (0-10)
    if margin is not None:
        m = margin * 100
        if m > 20:    score += 10; notes.append(f"Margin {m:.0f}%")
        elif m > 10:  score += 7
        elif m > 0:   score += 4
        else:         score += 0;  notes.append("Unprofitable")
    else:
        score += 3

    # ROE (0-10)
    if roe is not None:
        e = roe * 100
        if e > 20:    score += 10; notes.append(f"ROE {e:.0f}%")
        elif e > 10:  score += 7
        elif e > 0:   score += 4
        else:         score += 1
    else:
        score += 3

    # Debt/Equity (0-8) - lower is better
    if de is not None:
        if de < 50:    score += 8; notes.append("Low debt")
        elif de < 100: score += 5
        elif de < 200: score += 3
        else:          score += 1; notes.append("High debt")
    else:
        score += 3

    data = {
        "pe": round2(pe), "rev_growth": round2(rev_growth * 100 if rev_growth is not None else None),
        "margin": round2(margin * 100 if margin is not None else None),
        "roe": round2(roe * 100 if roe is not None else None),
        "debt_to_equity": round2(de)
    }
    return round(min(score, 50), 1), notes, data

# ---------- HORIZON + CONVICTION ----------
def decide_horizon(tech):
    """Pick the time horizon based on which signals dominate."""
    vola = tech.get("volatility") or 0
    m1 = tech.get("mom_1m") or 0
    rsi_v = tech.get("rsi") or 50
    price = tech.get("price"); ma200 = tech.get("ma200")
    long_ok = (ma200 is not None and price is not None and price > ma200)

    # intraday: high volatility + strong recent momentum
    if vola >= 3.0 and abs(m1) >= 5:
        return "intraday", "High volatility + strong short-term momentum"
    # swing: recovering RSI + positive 1M momentum
    if 35 <= rsi_v <= 65 and m1 > 0:
        return "swing", "Recovering momentum in a tradeable range"
    # long_term: in uptrend above 200MA
    if long_ok:
        return "long_term", "Established uptrend, suited to holding"
    # default fallback
    return "swing", "Mixed signals - monitor on swing timeframe"

def conviction(total):
    if total >= 75: return "Strong", "🟢"
    if total >= 55: return "Moderate", "🟡"
    return "Weak", "⚪"

def expected_window(horizon):
    return {
        "intraday":  "Hours to 1-2 days",
        "swing":     "1-6 weeks",
        "long_term": "6-18+ months",
    }.get(horizon, "Varies")

# ---------- per-ticker ----------
def analyze(ticker):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1y")
        if hist is None or hist.empty or len(hist) < 30:
            print(f"  [skip] {ticker}: insufficient history")
            return None

        tscore, tnotes, tech = technical_score(hist)
        fscore, fnotes, fund = fundamental_score(t)
        total = round(tscore + fscore, 1)

        horizon, hreason = decide_horizon(tech)
        conv_label, conv_emoji = conviction(total)

        rec = {
            "ticker": ticker,
            "total_score": total,
            "technical_score": tscore,
            "fundamental_score": fscore,
            "horizon": horizon,
            "expected_window": expected_window(horizon),
            "horizon_reason": hreason,
            "conviction": conv_label,
            "conviction_emoji": conv_emoji,
            "tech_notes": tnotes[:4],
            "fund_notes": fnotes[:4],
            "technicals": tech,
            "fundamentals": fund,
        }
        print(f"  [ok]   {ticker}: {total}/100 {conv_emoji} {conv_label} -> {horizon}")
        return rec
    except Exception as e:
        print(f"  [FAIL] {ticker}: {e}")
        traceback.print_exc()
        return None

# ---------- main ----------
def main():
    print(f"Analyzing {len(WATCHLIST)} tickers for suggestions...")
    recs = []
    for tk in WATCHLIST:
        r = analyze(tk)
        if r: recs.append(r)

    # sort best score first
    recs.sort(key=lambda x: x["total_score"], reverse=True)

    # bucket by horizon (top picks per style)
    buckets = {"intraday": [], "swing": [], "long_term": []}
    for r in recs:
        buckets[r["horizon"]].append(r)

    data = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "suggestions": recs,
        "by_horizon": buckets,
        "top_picks": recs[:5],
    }
    with open("suggestions.json", "w") as f:
        json.dump(data, f, indent=2)
    print("")
    print(f"Wrote suggestions.json with {len(recs)} scored stocks.")

if __name__ == "__main__":
    main()
