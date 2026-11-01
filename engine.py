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
    """Interactive, browser-only Stage 1 dashboard; no exposed API secrets."""
    # The dashboard is static but interactive: it displays the last completed
    # data refresh and can be opened any time without running a workflow.
    # Images are the exact same Stage 1 charts from chart().
    safe=[]
    for item in results:
        symbol=str(item["symbol"])
        if not symbol or not all(c.isalnum() or c in ".-" for c in symbol):
            raise ValueError("Invalid symbol for dashboard")
        safe.append({"symbol":symbol,
                     "session_date":item.get("session_date",""),
                     "error":item.get("error",""),
                     "patterns":[p["pattern"] for p in item.get("annotations",[])]})
    data=json.dumps(safe,ensure_ascii=False).replace("<","\\u003c")
    page="""<!doctype html>
<html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>METHOD 20 | Stage 1 Dashboard</title>
<style>
:root{font-family:Arial,system-ui,sans-serif;color:#172331;background:#f1f5f9}
*{box-sizing:border-box}body{margin:0}header{background:#101d31;color:white;padding:22px 4vw}
header h1{margin:0;font-size:1.65rem}header p{margin:7px 0 0;color:#cbd5e1}
main{max-width:1510px;margin:auto;padding:16px}
.controls{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:14px}
input,select,button{font:inherit;border-radius:9px;padding:11px;border:1px solid #cbd5e1;background:white}
input{flex:1;min-width:160px}button{cursor:pointer}
button:disabled{opacity:.35;cursor:not-allowed}
.panel{background:white;border-radius:14px;padding:15px;box-shadow:0 2px 12px #15243a10}
.meta{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin-bottom:12px}
.meta h2{margin:0;font-size:1.5rem;direction:ltr}
small{color:#64748b}.pill{background:#e8eef8;border-radius:30px;padding:6px 11px;font-size:12px}
img{width:100%;height:auto;display:block}
.hint{font-size:13px;color:#64748b;margin-top:14px}
#error{color:#b42318;display:none}
@media(max-width:650px){header{padding:17px}main{padding:8px}.panel{padding:8px}}
</style></head><body><header>
<h1>METHOD 20 | שכבה 1</h1>
<p>דשבורד גרפים אינטראקטיבי • 95 נרות יומיים • SMA20 • Volume • CCI(14)</p>
</header><main>
<div class="controls">
<label for="ticker">מניה</label>
<select id="ticker" aria-label="בחר מניה"></select>
<input id="search" type="search" placeholder="חיפוש מניה..." aria-label="חיפוש מניה">
<label for="filter">סינון</label>
<select id="filter"><option value="all">כל המניות</option>
<option value="patterns">עם סימון תבנית</option>
<option value="none">ללא סימון תבנית</option></select>
<button id="previous" type="button">הקודמת</button>
<button id="next" type="button">הבאה</button>
</div><section class="panel">
<div class="meta"><h2 id="name"></h2><span class="pill" id="date"></span>
<span class="pill" id="pattern"></span><small id="count"></small></div>
<div id="error"></div><img id="chart" alt="גרף מניה בשכבה 1" loading="eager">
<p class="hint">הנתונים נכונים למועד העדכון המצוין. פתיחת הדף או החלפת מניה אינה מושכת נתוני מסחר חדשים.</p>
</section></main>
<script id="report-data" type="application/json">__DATA__</script>
<script>
(() => {
  'use strict';
  const all=JSON.parse(document.getElementById('report-data').textContent);
  const byId=id=>document.getElementById(id);
  let visible=[],current='';
  const fromUrl=new URLSearchParams(location.search).get('ticker');
  function refreshOptions(){
    const query=byId('search').value.trim().toUpperCase();
    const filter=byId('filter').value;
    visible=all.filter(x=>x.symbol.includes(query)&&
      (filter==='all'||(filter==='patterns'?x.patterns.length>0:x.patterns.length===0)));
    const picker=byId('ticker');
    picker.replaceChildren();
    visible.forEach(x=>{const option=document.createElement('option');
      option.value=x.symbol;option.textContent=x.symbol;picker.appendChild(option)});
    current=visible.some(x=>x.symbol===current)?current:(visible[0]?.symbol||'');
    show(current);
  }
  function show(symbol){
    current=symbol;
    const item=visible.find(x=>x.symbol===symbol);
    byId('ticker').value=symbol;
    const i=visible.findIndex(x=>x.symbol===symbol);
    byId('previous').disabled=i<=0;
    byId('next').disabled=i<0||i===visible.length-1;
    byId('count').textContent=visible.length?(i+1)+' / '+visible.length:'0 מניות';
    byId('name').textContent=item?.symbol||'אין מניות התואמות לסינון';
    byId('date').textContent=item?.session_date?'נתוני מסחר: '+item.session_date:'אין תאריך נתונים';
    byId('pattern').textContent=item?.patterns?.length?'תבניות: '+item.patterns.join(', '):'ללא תבנית מסומנת';
    byId('error').style.display=item?.error?'block':'none';
    byId('error').textContent=item?.error||'';
    const img=byId('chart');
    img.hidden=!item||Boolean(item.error);
    if(item&&!item.error){img.src='charts/'+encodeURIComponent(item.symbol)+'.png';img.alt='גרף '+item.symbol+' עם SMA20, Volume, CCI ותבניות';}
    else img.removeAttribute('src');
    if(item){const url=new URL(location.href);url.searchParams.set('ticker',symbol);history.replaceState(null,'',url);}
  }
  byId('search').addEventListener('input',refreshOptions);
  byId('filter').addEventListener('change',refreshOptions);
  byId('ticker').addEventListener('change',e=>show(e.target.value));
  byId('previous').addEventListener('click',()=>{const i=visible.findIndex(x=>x.symbol===current);if(i>0)show(visible[i-1].symbol);});
  byId('next').addEventListener('click',()=>{const i=visible.findIndex(x=>x.symbol===current);if(i>=0&&i<visible.length-1)show(visible[i+1].symbol);});
  current=all.some(x=>x.symbol===fromUrl)?fromUrl:all[0]?.symbol||'';
  refreshOptions();
})();
</script></body></html>""".replace("__DATA__",data)
    (OUT/"index.html").write_text(page,encoding="utf-8")
    # Keep compatibility with the existing pipeline / artifact consumers.
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
