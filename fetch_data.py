#!/usr/bin/env python3
"""
Daily market data fetcher. Writes data.json for the dashboard.
Adds: market-cap classification, swing/intraday/long-term trade levels,
and a more engaging daily brief.
Free-tier friendly: yfinance (quotes/financials/cap) + SEC EDGAR (8-K).
"""
import json, datetime, os
import yfinance as yf
import pandas as pd
import requests

# ---- CONFIG (edit these) ----
WATCHLIST = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"]   # <-- your tickers
SEC_UA = "your-name your-email@example.com"             # SEC requires a real UA
# -----------------------------

# ---------- indicators ----------
def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    return round(float(100 - (100 / (1 + rs.iloc[-1]))), 1)

def atr(hist, period=14):
    """Average True Range — measures volatility, used to size stops/targets."""
    high, low, close = hist["High"], hist["Low"], hist["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([(high - low),
                    (high - prev_close).abs(),
                    (low - prev_close).abs()], axis=1).max(axis=1)
    return round(float(tr.rolling(period).mean().iloc[-1]), 2)

# ---------- 1) market-cap classification ----------
def classify_cap(market_cap):
    """Standard US market-cap tiers."""
    if market_cap is None:
        return "Unknown", None
    b = market_cap / 1e9  # to billions
    if   b >= 200: tier = "Mega"    # >= $200B
    elif b >= 10:  tier = "Large"   # $10B – $200B
    elif b >= 2:   tier = "Mid"     # $2B – $10B
    else:          tier = "Small"   # < $2B
    # pretty string
    if b >= 1000:  s = f"${b/1000:.2f}T"
    elif b >= 1:   s = f"${b:.1f}B"
    else:          s = f"${market_cap/1e6:.0f}M"
    return tier, s

# ---------- 2) trade-bucket levels (entry / target / stop) ----------
def round2(x): return round(float(x), 2)

def build_trade_buckets(price, atr_val):
    """
    ATR-based mechanical levels for 3 styles. NOT advice — pure math.
    Risk:Reward shown is target_distance / stop_distance.
    """
    if not price or not atr_val:
        return {}

    def setup(entry_mult, stop_mult, target_mult):
        entry  = price                       # reference = last close
        stop   = price - stop_mult * atr_val
        target = price + target_mult * atr_val
        risk   = entry - stop
        reward = target - entry
        rr = round(reward / risk, 1) if risk > 0 else None
        return {"entry": round2(entry), "stop": round2(stop),
                "target": round2(target), "rr": rr}

    return {
        # intraday: tight stop (1 ATR), modest target (1.5 ATR)
        "intraday":  setup(1, 1.0, 1.5),
        # swing: medium stop (1.5 ATR), larger target (3 ATR)
        "swing":     setup(1, 1.5, 3.0),
        # long_term: wide stop (3 ATR), big target (8 ATR)
        "long_term": setup(1, 3.0, 8.0),
    }

# ---------- per-ticker build ----------
def build_ticker(ticker):
    t = yf.Ticker(ticker)
    hist = t.history(period="1y")
    if hist.empty:
        return None, None, None

    price = round2(hist["Close"].iloc[-1])
    prev = float(hist["Close"].iloc[-2])
    change_pct = round((price - prev) / prev * 100, 2)

    # market cap
    mcap = None
    try:
        info = t.fast_info
        mcap = getattr(info, "market_cap", None) or info.get("market_cap")
    except Exception:
        try: mcap = t.info.get("marketCap")
        except Exception: mcap = None
    cap_tier, cap_str = classify_cap(mcap)

    # indicators
    r = rsi(hist["Close"])
    a = atr(hist)
    ma200 = float(hist["Close"].rolling(200).mean().iloc[-1])
    vs_200 = round((price - ma200) / ma200 * 100, 1)   # % above/below as a number
    hi52 = float(hist["Close"].max()); lo52 = float(hist["Close"].min())
    pos52 = round((price - lo52) / (hi52 - lo52) * 100, 0)

    # signal (transparent heuristic, NOT a prediction)
    if r < 35 and price > ma200:
        signal = "keeper"
    elif r > 70:
        signal = "dip-risk"
    else:
        signal = "watch"

    quote = {"ticker": ticker, "price": price, "change_pct": change_pct,
             "cap_tier": cap_tier, "market_cap_str": cap_str}

    screen = {"ticker": ticker, "rsi": r, "vs_200ma": vs_200,
              "pos_52w_pct": pos52, "signal": signal,
              "cap_tier": cap_tier, "market_cap_str": cap_str}

    trade = {"ticker": ticker, "atr": a, "buckets": build_trade_buckets(price, a)}

    return quote, screen, trade

# ---------- SEC 8-K filings ----------
def fetch_sec_8k(ticker):
    try:
        m = requests.get("https://www.sec.gov/files/company_tickers.json",
                         headers={"User-Agent": SEC_UA}, timeout=15).json()
        cik = next((str(v["cik_str"]).zfill(10) for v in m.values()
                    if v["ticker"] == ticker), None)
        if not cik: return []
        sub = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json",
                           headers={"User-Agent": SEC_UA}, timeout=15).json()
        recent = sub["filings"]["recent"]; out = []
        for form, date in zip(recent["form"], recent["filingDate"]):
            if form == "8-K":
                out.append({"headline": f"{ticker} 8-K filed {date} (material event)",
                            "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=8-K"})
            if len(out) >= 3: break
        return out
    except Exception:
        return []

# ---------- earnings ----------
def fetch_earnings(ticker):
    try:
        cal = yf.Ticker(ticker).calendar
        if isinstance(cal, dict) and cal.get("Earnings Date"):
            d = cal["Earnings Date"]; d = d[0] if isinstance(d, list) else d
            return {"ticker": ticker, "date": str(d)}
    except Exception:
        pass
    return None

# ---------- 3) engaging daily brief ----------
def build_brief(quotes, screen):
    if not quotes:
        return "🧭 No data yet — run the fetcher to populate your dashboard."

    movers = sorted(quotes, key=lambda x: abs(x["change_pct"]), reverse=True)
    top = movers[0]
    gainers = [q for q in quotes if q["change_pct"] > 0]
    losers  = [q for q in quotes if q["change_pct"] < 0]
    keepers = [s["ticker"] for s in screen if s["signal"] == "keeper"]
    dips    = [s["ticker"] for s in screen if s["signal"] == "dip-risk"]

    # overall mood emoji drives the hero animation
    if len(keepers) >= len(dips): mood = "🟢"
    elif len(dips) > len(keepers): mood = "🔴"
    else: mood = "🟡"

    arrow = "🚀" if top["change_pct"] > 0 else "📉"
    lines = []
    lines.append(f"{mood} Good day, SRIHARI! Here's your market pulse.")
    lines.append(f"{arrow} Today's headline mover is {top['ticker']} at "
                 f"{top['change_pct']:+.2f}% ({top['cap_tier']} cap).")
    lines.append(f"📊 Breadth: {len(gainers)} up vs {len(losers)} down on your watchlist.")
    if keepers:
        lines.append(f"💚 Strength (oversold-in-uptrend): {', '.join(keepers)}.")
    if dips:
        lines.append(f"⚠️ Pullback risk (overbought): {', '.join(dips)}.")
    lines.append("🔎 Tip: check the 8-K feed for leadership or material events. "
                 "Signals are heuristics, not advice.")
    return "  
".join(lines)   # two-space + newline = line breaks in the UI

# ---------- main ----------
def main():
    quotes, screen, trades, news, earnings = [], [], [], [], []
    for tk in WATCHLIST:
        q, s, tr = build_ticker(tk)
        if q: quotes.append(q)
        if s: screen.append(s)
        if tr: trades.append(tr)
        news += fetch_sec_8k(tk)
        e = fetch_earnings(tk)
        if e: earnings.append(e)

    data = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
                          .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "brief": build_brief(quotes, screen),
        "quotes": quotes,
        "screen": screen,
        "trades": trades,
        "news": news,
        "earnings": earnings,
    }
    with open("data.json", "w") as f:
        json.dump(data, f, indent=2)
    print("Wrote data.json with", len(quotes), "tickers.")

if __name__ == "__main__":
    main()
