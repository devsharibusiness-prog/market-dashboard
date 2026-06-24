#!/usr/bin/env python3
"""
Daily market data fetcher. Writes data.json for dashboard.html.
Free-tier friendly: uses yfinance (quotes/financials) + SEC EDGAR (8-K).
Plug in Finnhub/NewsAPI/X keys where marked to enrich.
"""
import json, datetime, os
import yfinance as yf
import pandas as pd
import requests

# ---- CONFIG (you will edit these in Phase 6) ----
WATCHLIST = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"]   # <-- your tickers
SEC_UA = "your-name your-email@example.com"             # SEC requires a real UA
FINNHUB_KEY = os.getenv("FINNHUB_KEY", "")              # optional
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")              # optional
# -------------------------------------------------

def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    return round(float(100 - (100 / (1 + rs.iloc[-1]))), 1)

def build_quote_and_screen(ticker):
    t = yf.Ticker(ticker)
    hist = t.history(period="1y")
    if hist.empty:
        return None, None
    price = round(float(hist["Close"].iloc[-1]), 2)
    prev = float(hist["Close"].iloc[-2])
    change_pct = round((price - prev) / prev * 100, 2)

    r = rsi(hist["Close"])
    ma200 = float(hist["Close"].rolling(200).mean().iloc[-1])
    vs_200 = "above 200MA" if price > ma200 else "below 200MA"
    hi52 = float(hist["Close"].max()); lo52 = float(hist["Close"].min())
    pos52 = round((price - lo52) / (hi52 - lo52) * 100, 0)

    # --- transparent heuristic, NOT a prediction ---
    if r < 35 and price > ma200:
        signal = "keeper"        # oversold but in uptrend
    elif r > 70:
        signal = "dip-risk"      # overbought, may pull back
    else:
        signal = "watch"

    quote = {"ticker": ticker, "price": price, "change_pct": change_pct}
    screen = {"ticker": ticker, "rsi": r, "vs_200ma": vs_200,
              "pos_52w_pct": pos52, "signal": signal}
    return quote, screen

def fetch_sec_8k(ticker):
    """Pull recent 8-K filings (material events incl. leadership changes)."""
    try:
        # Map ticker -> CIK
        m = requests.get("https://www.sec.gov/files/company_tickers.json",
                         headers={"User-Agent": SEC_UA}, timeout=15).json()
        cik = next((str(v["cik_str"]).zfill(10) for v in m.values()
                    if v["ticker"] == ticker), None)
        if not cik:
            return []
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        sub = requests.get(url, headers={"User-Agent": SEC_UA}, timeout=15).json()
        recent = sub["filings"]["recent"]
        out = []
        for form, date, acc in zip(recent["form"], recent["filingDate"],
                                   recent["accessionNumber"]):
            if form == "8-K":
                out.append({
                    "headline": f"{ticker} 8-K filed {date} (material event)",
                    "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=8-K"
                })
            if len(out) >= 3:
                break
        return out
    except Exception:
        return []

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

def main():
    quotes, screen, news, earnings = [], [], [], []
    for tk in WATCHLIST:
        q, s = build_quote_and_screen(tk)
        if q: quotes.append(q)
        if s: screen.append(s)
        news += fetch_sec_8k(tk)
        e = fetch_earnings(tk)
        if e: earnings.append(e)

    # Simple auto-generated brief from the screen
    movers = sorted(quotes, key=lambda x: abs(x["change_pct"]), reverse=True)[:3]
    mover_txt = ", ".join(f'{m["ticker"]} {m["change_pct"]:+}%' for m in movers)
    keepers = [s["ticker"] for s in screen if s["signal"] == "keeper"]
    dips    = [s["ticker"] for s in screen if s["signal"] == "dip-risk"]
    brief = (f"Biggest watchlist movers: {mover_txt or 'n/a'}. "
             f"Oversold-in-uptrend signals: {', '.join(keepers) or 'none'}. "
             f"Overbought (pullback risk): {', '.join(dips) or 'none'}. "
             f"Check 8-K filings for any leadership/material events. "
             f"Signals are heuristics, not advice.")

    data = {
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M %Z"),
        "brief": brief,
        "quotes": quotes,
        "screen": screen,
        "news": news,
        "earnings": earnings,
    }
    with open("data.json", "w") as f:
        json.dump(data, f, indent=2)
    print("Wrote data.json with", len(quotes), "tickers.")

if __name__ == "__main__":
    main()
