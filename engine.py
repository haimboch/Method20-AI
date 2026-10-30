import os, json, time, html
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.ticker import FormatStrFormatter
from stage1_patterns import annotations

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"output"

def daily_session_dates(epoch_millis):
    """Massive daily aggregates use a UTC date label, not a NY local time."""
    return pd.to_datetime(epoch_millis,unit="ms",utc=True).dt.date

def fetch(symbol):
    """Fetch split-adjusted DAILY OHLCV from Massive. No key is printed or saved."""
    from datetime import datetime, timedelta, time as clock_time
    from zoneinfo import ZoneInfo
    import requests
    ny = datetime.now(ZoneInfo("America/New_York"))
    end = ny.date()
    start = end - timedelta(days=520)
    key = os.getenv("MASSIVE_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Missing MASSIVE_API_KEY GitHub Actions secret")
    url = (f"https://api.massive.com/v2/aggs/ticker/{symbol}/range/1/day/"
           f"{start.isoformat()}/{end.isoformat()}")
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    # Avoid hidden repeated 429 retries; respond to throttling explicitly.
    retry=Retry(total=2,backoff_factor=1,
                status_forcelist=(500,502,503,504),
                allowed_methods=frozenset(["GET"]))
    max_429_retries=4
    response=None
    with requests.Session() as session:
        session.mount("https://",HTTPAdapter(max_retries=retry))
        for attempt in range(max_429_retries+1):
            response=session.get(
                url,
                headers={"Authorization": f"Bearer {key}"},
                params={"adjusted": "true", "sort": "asc", "limit": 50000},
                timeout=40
            )
            if response.status_code!=429:
                break
            if attempt==max_429_retries:
                raise RuntimeError(
                    f"Massive rate limit (HTTP 429) persisted for {symbol} "
                    f"after {max_429_retries+1} requests; check API plan and shared-key usage"
                )
            retry_after=response.headers.get("Retry-After","")
            try:
                delay=float(retry_after)
                if not 1<=delay<=300:
                    delay=75.0
            except (ValueError,TypeError):
                delay=75.0
            print(f"MASSIVE_429 symbol={symbol} attempt={attempt+1} "
                  f"wait_seconds={delay:.0f}",flush=True)
            time.sleep(delay)
    response.raise_for_status()
    data = response.json()
    if data.get("status") == "ERROR":
        raise ValueError(f"Market data provider error: {data.get('message','unknown')}")
    bars = data.get("results", [])
    if not bars:
        raise ValueError("Massive returned no OHLCV daily data")
    d = pd.DataFrame(bars).rename(columns={
        "t": "date", "o": "open", "h": "high", "l": "low",
        "c": "close", "v": "volume"
    })
    # Massive daily aggregate timestamps identify the UTC calendar trading date.
    # Converting midnight UTC to NY time shifts the session label to yesterday.
    d["date"] = daily_session_dates(d["date"])
    if ny.weekday() < 5 and ny.time() < clock_time(16, 15):
        d = d[d.date < ny.date()]
    d = d[["date", "open", "high", "low", "close", "volume"]]
    d = d.sort_values("date").drop_duplicates("date")
    for column in ["open", "high", "low", "close", "volume"]:
        d[column] = pd.to_numeric(d[column], errors="coerce")
    d = d.dropna()
    if len(d) < 60:
        raise ValueError(f"Insufficient completed daily bars: {len(d)} (need 60 for supported short-history analysis)")
    if not ((d.high >= d[["open", "close", "low"]].max(axis=1)) &
            (d.low <= d[["open", "close", "high"]].min(axis=1))).all():
        raise ValueError("Invalid OHLC values from provider")
    return d.reset_index(drop=True)

def indicators(d):
    d=d.copy()
    d["sma20"]=d.close.rolling(20).mean()
    d["vol20"]=d.volume.rolling(20).mean()
    tp=(d.high+d.low+d.close)/3
    avg=tp.rolling(14).mean()
    mad=tp.rolling(14).apply(lambda x: np.mean(np.abs(x-x.mean())),raw=True)
    d["cci"]=((tp-avg)/(0.015*mad.replace(0,np.nan)))
    return d

def chart(d,symbol,path,a=None,zone=None):
    """Exactly 95 daily Japanese candles, SMA20, volume and CCI(14)."""
    if len(d)<95:
        raise ValueError(f"{symbol}: only {len(d)} daily bars; 95 required")
    view=d.tail(95).reset_index(drop=True)
    fig,(ax,vax,cax)=plt.subplots(3,1,figsize=(15,10),sharex=True,
                                  gridspec_kw={"height_ratios":[6,1.5,1.8]})
    for i,x in view.iterrows():
        color="#12805c" if x.close>=x.open else "#c44747"
        ax.vlines(i,x.low,x.high,color=color,lw=1)
        ax.add_patch(Rectangle((i-.33,min(x.open,x.close)),.66,
                               max(abs(x.close-x.open),.001),
                               color=color))
        vax.bar(i,x.volume,color=color,width=.75)
    ax.plot(np.arange(95),view.sma20,color="#e5a522",lw=2,
            label="SMA20")
    # Stage 1: observational marks only. No trend or trade-state inference.
    marks=annotations(view)
    for mark in marks:
        first,last=mark["start"],mark["end"]
        bottom=float(view.low.iloc[first:last+1].min())
        top=float(view.high.iloc[first:last+1].max())
        span=max(top-bottom,1e-6)
        ax.add_patch(Rectangle((first-.47,bottom-.04*span),
                               last-first+.94,span*1.08,fill=False,
                               edgecolor="black",lw=2.0,zorder=9))
        ax.annotate(mark["pattern"],((first+last)/2,top),
                    xytext=(0,12),textcoords="offset points",
                    ha="center",va="bottom",fontsize=8,fontweight="bold",
                    color="#171717",zorder=10)
    ax.margins(y=.16)
    ax.yaxis.set_major_formatter(FormatStrFormatter("%.2f"))
    ax.set_title(symbol+" | 1D | "+str(view.iloc[-1].date),fontsize=16)
    ax.grid(alpha=.17)
    ax.legend(loc="upper left")
    vax.set_ylabel("VOL")
    vax.grid(axis="y",alpha=.17)
    cax.plot(np.arange(95),view.cci,color="#7359b8",lw=1.3)
    cax.axhline(-100,color="#c44747",ls="--",lw=.8)
    cax.axhline(100,color="#12805c",ls="--",lw=.8)
    cax.yaxis.set_major_formatter(FormatStrFormatter("%.2f"))
    cax.set_ylabel("CCI(14)")
    cax.grid(alpha=.17)
    ticks=list(range(0,95,12))
    cax.set_xticks(ticks,[str(view.date.iloc[i])[5:] for i in ticks],rotation=40)
    fig.tight_layout()
    fig.savefig(path,dpi=175)
    plt.close(fig)


def render(results,portfolio=None):
    """Plain HTML report; chart only, no trade status or zones."""
    cards=[]
    for item in results:
        symbol=html.escape(item["symbol"])
        if "error" in item:
            cards.append("<section><h2>"+symbol+"</h2><p>Chart unavailable</p></section>")
        else:
            cards.append('<section><h2>'+symbol+'</h2><img src="charts/'+symbol+
                         '.png" alt="95 daily candlesticks SMA20 Volume CCI14"></section>')
    page=('<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">'
          +'<meta name="viewport" content="width=device-width,initial-scale=1">'
          +'<title>METHOD 20 | Daily Charts</title>'
          +'<style>body{font-family:Arial,sans-serif;background:#f3f5f9;'
          +'color:#172331;margin:0;padding:16px}main{max-width:1350px;margin:auto}'
          +'section{background:white;padding:16px;margin:16px 0;border-radius:14px}'
          +'img{width:100%;height:auto;display:block}</style></head>'
          +'<body><main><h1>METHOD 20 | Daily Charts</h1>'
          +''.join(cards)+'</main></body></html>')
    (OUT/"report.html").write_text(page,encoding="utf-8")


def main():
    OUT.mkdir(exist_ok=True)
    (OUT/"charts").mkdir(exist_ok=True)
    symbols=[s.strip().upper() for s in (ROOT/"watchlist.txt").read_text().splitlines()
             if s.strip() and not s.startswith("#")]
    if len(symbols)!=len(set(symbols)):
        raise ValueError("watchlist.txt contains duplicate symbols")
    if not 1<=len(symbols)<=40:
        raise ValueError("Watchlist size must stay between 1 and 40 tickers")
    print(f"WATCHLIST_COUNT={len(symbols)}",flush=True)
    results=[]
    request_interval=float(os.getenv("MASSIVE_REQUEST_INTERVAL_SEC","20"))
    next_request_at=0.0
    expected=os.getenv("EXPECTED_SESSION_DATE","").strip()
    for symbol in symbols:
        try:
            remaining=next_request_at-time.monotonic()
            if remaining>0:time.sleep(remaining)
            next_request_at=time.monotonic()+request_interval
            d=indicators(fetch(symbol))
            if expected and str(d.iloc[-1].date)!=expected:
                raise ValueError("Stale latest daily candle: expected "+expected+
                                 ", got "+str(d.iloc[-1].date))
            chart(d,symbol,OUT/"charts"/f"{symbol}.png")
            marks=annotations(d)
            results.append({"symbol":symbol,"session_date":str(d.iloc[-1].date),
                            "candles":95,"annotations":marks})
            print(f"{symbol}: {d.iloc[-1].date} 95 bars",flush=True)
        except Exception as e:
            print(f"{symbol}: ERROR {type(e).__name__}: {e}",flush=True)
            results.append({"symbol":symbol,"error":str(e)})
    render(results)
    (OUT/"results.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),
                                    encoding="utf-8")
    errors=[r["symbol"] for r in results if "error" in r]
    session_date=expected or next((r["session_date"] for r in results
                                   if "session_date" in r),"")
    metadata={"report_type":"CHART_WITH_STAGE1_MARKS","candles_per_chart":95,
              "session_date":session_date,"symbols":symbols,
              "expected_ticker_count":len(symbols),
              "analyzed_ticker_count":len(symbols)-len(errors),
              "failed_symbols":errors,"complete":not errors}
    (OUT/"metadata.json").write_text(json.dumps(metadata,indent=2),encoding="utf-8")
    print("REPORT_HEALTH",json.dumps(metadata),flush=True)
    if errors:raise SystemExit("Incomplete daily chart report: "+", ".join(errors))

if __name__=="__main__":
    main()
