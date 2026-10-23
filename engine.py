import os, json, time, html
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"output"

def fetch(symbol):
    # Request two years of daily data for enough indicator warm-up.
    # Do not treat an in-progress US trading session as a completed daily candle.
    from datetime import datetime, time as dtime
    from zoneinfo import ZoneInfo
    import yfinance as yf
    eastern = datetime.now(ZoneInfo("America/New_York"))
    d = yf.Ticker(symbol).history(
        period="2y", interval="1d", auto_adjust=True,
        actions=False, prepost=False, timeout=25
    )
    if d is None or d.empty:
        raise ValueError("Yahoo Finance returned no daily bars")
    if hasattr(d.columns, "nlevels") and d.columns.nlevels > 1:
        d.columns = d.columns.get_level_values(0)
    d = d.rename(columns={
        "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume"
    })
    d = d[["open", "high", "low", "close", "volume"]].copy()
    d["date"] = [x.date() for x in d.index]
    if eastern.weekday() < 5 and eastern.time() < dtime(16, 15):
        d = d[d.date < eastern.date()]
    d = d[["date", "open", "high", "low", "close", "volume"]]
    d = d.sort_values("date").drop_duplicates("date")
    for col in ["open", "high", "low", "close", "volume"]:
        d[col] = pd.to_numeric(d[col], errors="coerce")
    d = d.dropna()
    if len(d) < 160:
        raise ValueError(f"Need >=160 completed sessions; got {len(d)}")
    if not ((d.high >= d[["open", "close", "low"]].max(axis=1)) &
            (d.low <= d[["open", "close", "high"]].min(axis=1))).all():
        raise ValueError("Invalid OHLC values")
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

def bullish(d,i):
    x=d.iloc[i]
    span=max(float(x.high-x.low),1e-9)
    body=abs(x.close-x.open)
    green=x.close>x.open
    hammer=(min(x.open,x.close)-x.low >=2*body) and (x.high-max(x.open,x.close)<=body)
    engulf=False
    if i>0:
        prev=d.iloc[i-1]
        engulf=(green and prev.close<prev.open and x.open<=prev.close and x.close>=prev.open)
    return bool((green and (x.close-x.low)/span>=0.65 and body/span>=0.25) or hammer or engulf)

def classify(d,i):
    if i<160: return None
    cur,prev,older=d.iloc[i],d.iloc[i-1],d.iloc[i-2]
    if pd.isna(cur.sma20) or pd.isna(cur.cci) or pd.isna(prev.cci) or pd.isna(older.cci):
        return None
    cci_turn=cur.cci>prev.cci and prev.cci<=older.cci
    rising_volume=cur.volume>prev.volume or cur.volume>cur.vol20
    if not (bullish(d,i) and cci_turn and rising_volume): return None
    recent_down=d.close.iloc[i-5]<d.close.iloc[i-10] if i>=10 else False
    below=cur.close<cur.sma20
    bounce=(abs(cur.low/cur.sma20-1)<=0.025 and cur.close>=cur.sma20*0.98)
    if below and recent_down and min(d.cci.iloc[max(0,i-5):i+1]) < -100:
        kind="A: MEAN_REVERSION"
    elif bounce: kind="B: SMA20_BOUNCE"
    else: return None
    return {"setup":kind,"signal_date":str(cur.date),"high":float(cur.high),"low":float(cur.low),"status":"READY"}

def analyze(d):
    active=None
    last_event=None
    for i in range(160,len(d)):
        x=d.iloc[i]
        if active:
            up=bool(x.high>active["high"])
            down=bool(x.low<active["low"])
            if up or down:
                active["status"]="AMBIGUOUS" if up and down else ("INVALIDATED" if down else "TRIGGERED")
                active["event_date"]=str(x.date)
                last_event=active.copy()
                active=None
            continue
        signal=classify(d,i)
        if signal: active=signal
    x=d.iloc[-1]
    return {"symbol_date":str(x.date),"close":float(x.close),"sma20":float(x.sma20),"cci14":float(x.cci),"volume_ratio":float(x.volume/x.vol20),"change_5d_pct":float((x.close/d.close.iloc[-6]-1)*100),"change_21d_pct":float((x.close/d.close.iloc[-22]-1)*100),"active":active,"last_event":last_event}

def chart(d,symbol,path,a):
    d=d.tail(95).reset_index(drop=True)
    fig,(ax,vax,cax)=plt.subplots(3,1,figsize=(12,8),sharex=True,gridspec_kw={"height_ratios":[5,1.2,1.5]})
    for i,x in d.iterrows():
        color="#12805c" if x.close>=x.open else "#c44747"
        ax.vlines(i,x.low,x.high,color=color,lw=1)
        ax.add_patch(Rectangle((i-.33,min(x.open,x.close)),.66,max(abs(x.close-x.open),.001),color=color))
        vax.bar(i,x.volume,color=color,width=.75)
    ax.plot(np.arange(len(d)),d.sma20,color="#e5a522",lw=1.8,label="SMA20")
    if a and str(a["signal_date"])>=str(d.iloc[0].date):
        ax.axhline(a["high"],ls="--",color="#12805c",lw=1,label="reversal HIGH")
        ax.axhline(a["low"],ls="--",color="#c44747",lw=1,label="reversal LOW")
    ax.set_title(symbol+"  |  1D  |  "+str(d.iloc[-1].date))
    ax.legend(loc="upper left")
    ax.grid(alpha=.17)
    vax.set_ylabel("VOL")
    cax.plot(np.arange(len(d)),d.cci,color="#7359b8")
    cax.axhline(-100,color="#c44747",ls="--",lw=.8)
    cax.axhline(100,color="#12805c",ls="--",lw=.8)
    cax.set_ylabel("CCI14")
    ticks=list(range(0,len(d),max(1,len(d)//8)))
    cax.set_xticks(ticks,[str(d.date.iloc[i])[5:] for i in ticks],rotation=40)
    cax.grid(alpha=.17)
    fig.tight_layout()
    fig.savefig(path,dpi=160)
    plt.close(fig)

def render(results):
    cards=[]
    for r in results:
        sym=html.escape(r["symbol"])
        if "error" in r:
            cards.append(f'<section><h2>{sym}</h2><p class="err">נתונים לא זמינים: {html.escape(r["error"])}</p></section>')
            continue
        a=r["analysis"]
        active=a["active"]
        status=active["status"] if active else "NO ACTIVE SETUP"
        setup=active["setup"] if active else "אין סטאפ פעיל"
        old=a["last_event"]
        prior=(f'אירוע קודם: {html.escape(old["status"])} בתאריך {html.escape(old.get("event_date",""))}' if old else "אין אירוע קודם")
        cards.append(f'<section><h2>{sym} <small>{html.escape(status)}</small></h2><p>תאריך נר אחרון: {html.escape(a["symbol_date"])}</p><p>סגירה: ${a["close"]:.2f} | SMA20: ${a["sma20"]:.2f} | CCI14: {a["cci14"]:.1f} | Volume / Avg20: {a["volume_ratio"]:.2f}x</p><p>שינוי 5 ימים: {a["change_5d_pct"]:+.2f}% | שינוי 21 ימים: {a["change_21d_pct"]:+.2f}%</p><p>סטאפ: {html.escape(setup)}. {prior}</p><img src="charts/{sym}.png" alt="Daily chart for {sym}" loading="lazy"/></section>')
    document='''<!doctype html><html lang="he" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>METHOD 20</title><style>body{font-family:Arial,sans-serif;background:#f3f5f9;color:#172331;margin:0;padding:20px}main{max-width:1050px;margin:auto}section{background:white;padding:20px;margin:18px 0;border-radius:16px;box-shadow:0 1px 7px #0001}img{max-width:100%;height:auto}small{font-size:14px;color:#666}.err{color:#aa3333}p{line-height:1.65}</style><main><h1>METHOD 20 AI | דוח פיילוט</h1><p>מידע למחקר בלבד. ללא ביצוע עסקאות. סטאפים מזוהים בחוקים ניסיוניים. לא בוצע ניתוח חזותי באמצעות AI.</p>'''+''.join(cards)+'</main></html>'
    (OUT/"report.html").write_text(document,encoding="utf-8")

def main():
    OUT.mkdir(exist_ok=True)
    (OUT/"charts").mkdir(exist_ok=True)
    symbols=[s.strip().upper() for s in (ROOT/"watchlist.txt").read_text().splitlines() if s.strip() and not s.startswith("#")]
    results=[]
    for s in symbols:
        try:
            d=indicators(fetch(s))
            a=analyze(d)
            chart(d,s,OUT/"charts"/f"{s}.png",a["active"])
            results.append({"symbol":s,"analysis":a})
            print(f"{s}: {a['symbol_date']} {a['active']['status'] if a['active'] else 'NO ACTIVE SETUP'}")
        except Exception as e:
            results.append({"symbol":s,"error":str(e)})
            print(f"{s}: ERROR {e}",flush=True)
    render(results)
    (OUT/"results.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Report:",OUT/"report.html")
    if all("error" in x for x in results): raise SystemExit("All ticker downloads failed")

if __name__=="__main__":main()
