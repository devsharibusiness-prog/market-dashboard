#!/usr/bin/env python3
"""
fetch_data.py - writes data.json for the dashboard.
Provides: quotes (price, change, cap tier), screen (RSI, 52w, signal),
trade buckets (intraday/swing/long-term entry/target/stop + ATR),
earnings dates, SEC 8-K filings, and an engaging daily brief.

Pairs with suggest.py (which writes suggestions.json + market.json).
Free stack: yfinance + SEC EDGAR. Regex-free. No backslash-n inside strings.
Per-ticker try/except so one bad ticker never crashes the run.
NOT financial advice.
"""
import json
import datetime
import traceback
import yfinance as yf
import pandas as pd
import requests

# ============================================================
# CONFIG  <-- EDIT THESE
# ============================================================
WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL",
    "GOOG", "META", "TSLA", "AVGO", "BRK.B",
    "LLY", "JPM", "V", "MA", "WMT",
    "XOM", "ORCL", "NFLX", "COST", "JNJ",
    "PG", "HD", "ABBV", "BAC", "KO",

    "CRM", "ADBE", "AMD", "QCOM", "TXN",
    "AMGN", "INTU", "LOW", "SPGI", "CAT",
    "GE", "BKNG", "TMO", "SCHW", "PGR",
    "GILD", "VRTX", "HON", "DE", "SYK",
    "PANW", "ANET", "LRCX", "MU", "ADP",

    "DKNG", "RDDT", "CELH", "ARM", "APP",
    "SOFI", "HOOD", "CAVA", "RKLB", "PLTR",
    "UBER", "LYFT", "FSLR", "WING", "EME",
    "DUOL", "PINS", "BROS", "ELF", "FTAI",
    "ONON", "HIMS", "CRDO", "ASTS", "NXT",

    "IONQ", "RGTI", "QBTS", "SOUN", "ACHR",
    "JOBY", "LUNR", "RDW", "SATS", "BKSY",
    "AUR", "LAZR", "AEHR", "BTDR", "CLSK",
    "RIOT", "MARA", "UPWK", "FVRR", "COUR",
    "DNA", "OUST", "BLZE", "AMPL", "CRNC"
]
SEC_UA = "Srihari D devshari.business@gmail.com"     # SEC requires a REAL name + email
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

# ---------- indicators ----------
def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    val = 100 - (100 / (1 + rs.iloc[-1]))
    return round1(val) if pd.notna(val) else None

def atr(hist, period=14):
    high = hist["High"]
    low = hist["Low"]
    close = hist["Close"]
    prev = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev).abs()
    tr3 = (low - prev).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    val = tr.rolling(period).mean().iloc[-1]
    return round2(val) if pd.notna(val) else None

# ---------- market-cap classification ----------
def classify_cap(market_cap):
    if not market_cap or market_cap <= 0:
        return "Unknown", None
    b = market_cap / 1e9
    if b >= 200:
        tier = "Mega"
    elif b >= 10:
        tier = "Large"
    elif b >= 2:
        tier = "Mid"
    else:
        tier = "Small"
    if b >= 1000:
        s = "$" + str(round(b / 1000, 2)) + "T"
    elif b >= 1:
        s = "$" + str(round1(b)) + "B"
    else:
        s = "$" + str(round(market_cap / 1e6)) + "M"
    return tier, s

def get_market_cap(t):
    try:
        fi = t.fast_info
        mc = None
        try:
            mc = fi.get("market_cap")
        except Exception:
            mc = getattr(fi, "market_cap", None)
        if mc:
            return mc
    except Exception:
        pass
    try:
        info = t.info
        mc = info.get("marketCap")
        if mc:
            return mc
    except Exception:
        pass
    return None

# ---------- trade-bucket levels ----------
def build_trade_buckets(price, atr_val):
    if not price or not atr_val:
        return {}
    def setup(stop_mult, target_mult):
        entry = price
        stop = price - stop_mult * atr_val
        target = price + target_mult * atr_val
        risk = entry - stop
        reward = target - entry
        rr = round1(reward / risk) if risk > 0 else None
        return {"entry": round2(entry), "stop": round2(stop),
                "target": round2(target), "rr": rr}
    return {
        "intraday": setup(1.0, 1.5),
        "swing": setup(1.5, 3.0),
        "long_term": setup(3.0, 8.0),
    }

# ---------- per-ticker ----------
def build_ticker(ticker):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1y")
        if hist is None or hist.empty or len(hist) < 2:
            print("  [skip] " + ticker + ": no price history")
            return None, None, None

        price = round2(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2])
        change_pct = round2((price - prev) / prev * 100) if prev else 0.0

        mcap = get_market_cap(t)
        cap_tier, cap_str = classify_cap(mcap)

        r = rsi(hist["Close"])
        a = atr(hist)

        ma200 = None
        if len(hist) >= 200:
            ma200 = float(hist["Close"].rolling(200).mean().iloc[-1])
        vs_200 = round1((price - ma200) / ma200 * 100) if ma200 else None

        hi52 = float(hist["Close"].max())
        lo52 = float(hist["Close"].min())
        pos52 = round((price - lo52) / (hi52 - lo52) * 100) if hi52 != lo52 else 50

        if r is not None and ma200 and r < 35 and price > ma200:
            signal = "keeper"
        elif r is not None and r > 70:
            signal = "dip-risk"
        else:
            signal = "watch"

        quote = {"ticker": ticker, "price": price, "change_pct": change_pct,
                 "cap_tier": cap_tier, "market_cap_str": cap_str}
        screen = {"ticker": ticker, "rsi": r, "vs_200ma": vs_200,
                  "pos_52w_pct": pos52, "signal": signal,
                  "cap_tier": cap_tier, "market_cap_str": cap_str}
        trade = {"ticker": ticker, "atr": a, "buckets": build_trade_buckets(price, a)}

        print("  [ok]   " + ticker + ": $" + str(price) + " ("
              + str(change_pct) + "%) " + cap_tier + " cap, RSI " + str(r))
        return quote, screen, trade
    except Exception as e:
        print("  [FAIL] " + ticker + ": " + str(e))
        traceback.print_exc()
        return None, None, None

# ---------- SEC 8-K filings ----------
def fetch_sec_8k(ticker):
    try:
        m = requests.get("https://www.sec.gov/files/company_tickers.json",
                         headers={"User-Agent": SEC_UA}, timeout=15).json()
        cik = None
        for v in m.values():
            if v["ticker"] == ticker:
                cik = str(v["cik_str"]).zfill(10)
                break
        if not cik:
            return []
        sub = requests.get("https://data.sec.gov/submissions/CIK" + cik + ".json",
                           headers={"User-Agent": SEC_UA}, timeout=15).json()
        recent = sub["filings"]["recent"]
        out = []
        for form, date in zip(recent["form"], recent["filingDate"]):
            if form == "8-K":
                out.append({
                    "headline": ticker + " 8-K filed " + date + " (material event)",
                    "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK="
                           + cik + "&type=8-K",
                })
            if len(out) >= 3:
                break
        return out
    except Exception as e:
        print("  [news skip] " + ticker + ": " + str(e))
        return []

# ---------- earnings ----------
def fetch_earnings(ticker):
    try:
        cal = yf.Ticker(ticker).calendar
        if isinstance(cal, dict) and cal.get("Earnings Date"):
            d = cal["Earnings Date"]
            d = d[0] if isinstance(d, list) else d
            return {"ticker": ticker, "date": str(d)}
    except Exception:
        pass
    return None

# ---------- engaging daily brief ----------
def build_brief(quotes, screen):
    if not quotes:
        return "No data could be loaded today - check the workflow logs."
    movers = sorted(quotes, key=lambda x: abs(x["change_pct"]), reverse=True)
    top = movers[0]
    gainers = [q for q in quotes if q["change_pct"] > 0]
    losers = [q for q in quotes if q["change_pct"] < 0]
    keepers = [s["ticker"] for s in screen if s["signal"] == "keeper"]
    dips = [s["ticker"] for s in screen if s["signal"] == "dip-risk"]
    if len(keepers) >= len(dips):
        mood = chr(0x1F7E2)
    elif len(dips) > len(keepers):
        mood = chr(0x1F534)
    else:
        mood = chr(0x1F7E1)
    arrow = chr(0x1F680) if top["change_pct"] > 0 else chr(0x1F4C9)
    lines = []
    lines.append(mood + " Good day, SRIHARI! Here's your market pulse.")
    lines.append(arrow + " Today's headline mover is " + top["ticker"] + " at "
                 + ("+" if top["change_pct"] >= 0 else "") + str(top["change_pct"])
                 + "% (" + top["cap_tier"] + " cap).")
    lines.append(chr(0x1F4CA) + " Breadth: " + str(len(gainers)) + " up vs "
                 + str(len(losers)) + " down on your watchlist.")
    if keepers:
        lines.append(chr(0x1F49A) + " Strength (oversold-in-uptrend): " + ", ".join(keepers) + ".")
    if dips:
        lines.append(chr(0x26A0) + " Pullback risk (overbought): " + ", ".join(dips) + ".")
    lines.append(chr(0x1F50E) + " Tip: open the Suggestions section for scored ideas. Signals are heuristics, not advice.")
    sep = "  " + chr(10)
    return sep.join(lines)

# ---------- main ----------
def main():
    quotes, screen, trades, news, earnings = [], [], [], [], []
    print("Fetching " + str(len(WATCHLIST)) + " tickers...")
    for tk in WATCHLIST:
        q, s, tr = build_ticker(tk)
        if q:
            quotes.append(q)
        if s:
            screen.append(s)
        if tr:
            trades.append(tr)
        news += fetch_sec_8k(tk)
        e = fetch_earnings(tk)
        if e:
            earnings.append(e)

    data = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "brief": build_brief(quotes, screen),
        "quotes": quotes,
        "screen": screen,
        "trades": trades,
        "news": news,
        "earnings": earnings,
    }
    with open("data.json", "w") as f:
        json.dump(data, f, indent=2)
    print("")
    print("Wrote data.json with " + str(len(quotes)) + " of " + str(len(WATCHLIST)) + " tickers.")

if __name__ == "__main__":
    main()
