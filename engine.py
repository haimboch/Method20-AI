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
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {key}"},
        params={"adjusted": "true", "sort": "asc", "limit": 50000},
        timeout=40
    )
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
    d["date"] = pd.to_datetime(d["date"], unit="ms", utc=True).dt.tz_convert(
        "America/New_York"
    ).dt.date
    if ny.weekday() < 5 and ny.time() < clock_time(16, 15):
        d = d[d.date < ny.date()]
    d = d[["date", "open", "high", "low", "close", "volume"]]
    d = d.sort_values("date").drop_duplicates("date")
    for column in ["open", "high", "low", "close", "volume"]:
        d[column] = pd.to_numeric(d[column], errors="coerce")
    d = d.dropna()
    if len(d) < 160:
        raise ValueError(f"Insufficient completed daily bars: {len(d)} (need 160)")
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

from signals import analyze, classify, candle_pattern, transition
from checklist import build_checklist
from ai_review import review_chart
from levels import structure, scenario

def chart(d,symbol,path,a,levels=None):
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
    if levels:
        for j,z in enumerate(levels["support"]):
            ax.axhline(z["price"],color="#16815c",ls=":",lw=1.1,label="Support" if j==0 else None)
        for j,z in enumerate(levels["resistance"]):
            ax.axhline(z["price"],color="#b75a4c",ls=":",lw=1.1,label="Resistance" if j==0 else None)
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
        status=a["status"]
        setup=active["setup"] if active else "אין סטאפ פעיל"
        old=a["last_event"]
        prior=(f'אירוע קודם: {html.escape(old["status"])} בתאריך {html.escape(old.get("event_date",""))}' if old else "אין אירוע קודם")
        checkrows=''.join('<tr><td>'+html.escape(str(k))+'</td><td>'+html.escape(str(v))+'</td></tr>' for k,v,_ in r.get('checklist',[]))
        ai=r.get('ai_review',{'status':'NOT_CONFIGURED','text':'ניתוח AI לא הופעל.'})
        ai_txt=html.escape(ai.get('text',''))
        ai_stat=html.escape(ai.get('status','NOT_CONFIGURED'))
        lv=r.get("levels",{})
        outlook=r.get("outlook",{})
        def fmtlevels(values):
            return ", ".join("$"+format(v["price"],".2f") for v in values) if values else "אין רמה מאומתת בחלון הסריקה"
        support_text=html.escape(fmtlevels(lv.get("support",[])))
        resistance_text=html.escape(fmtlevels(lv.get("resistance",[])))
        bias_text=html.escape(outlook.get("bias","לא זמין"))
        reasons=html.escape(outlook.get("reason",""))
        bull=html.escape(outlook.get("bull_case",""))
        bear=html.escape(outlook.get("bear_case",""))

        cards.append(f'<section><h2>{sym} <small>{html.escape(status)}</small></h2><p>תאריך נר אחרון: {html.escape(a["symbol_date"])}</p><p>סגירה: ${a["close"]:.2f} | SMA20: ${a["sma20"]:.2f} | CCI14: {a["cci14"]:.1f} | Volume / Avg20: {a["volume_ratio"]:.2f}x</p><p>שינוי 5 ימים: {a["change_5d_pct"]:+.2f}% | שינוי 21 ימים: {a["change_21d_pct"]:+.2f}%</p><p>סטאפ: {html.escape(setup)}. {prior}</p><div class="panel"><h3>תמיכה והתנגדות</h3><p>תמיכות: {support_text}</p><p>התנגדויות: {resistance_text}</p><h3>תרחיש ליום הבא: {bias_text}</h3><p>{reasons}</p><p>תרחיש שורי: {bull}</p><p>תרחיש דובי: {bear}</p><small>תרחישים מותנים, לא תחזית הסתברותית מאומתת.</small></div><div class="panel"><h3>צ׳קליסט METHOD 20</h3><table>{checkrows}</table></div><img src="charts/{sym}.png" alt="Daily chart for {sym}" loading="lazy"/><div class="panel"><h3>ניתוח תמונת הגרף באמצעות AI | {ai_stat}</h3><p>{ai_txt}</p></div></section>')
    document='''<!doctype html><html lang="he" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>METHOD 20</title><style>body{font-family:Arial,sans-serif;background:#f3f5f9;color:#172331;margin:0;padding:20px}main{max-width:1050px;margin:auto}section{background:white;padding:20px;margin:18px 0;border-radius:16px;box-shadow:0 1px 7px #0001}img{max-width:100%;height:auto}small{font-size:14px;color:#666}.panel{background:#f5f7fa;padding:12px;border-radius:10px;margin:12px 0}table{width:100%;border-collapse:collapse}td{padding:8px;border-bottom:1px solid #ddd}td:first-child{font-weight:bold}.err{color:#aa3333}p{line-height:1.65}</style><main><h1>METHOD 20 AI | דוח פיילוט</h1><p>מידע למחקר בלבד. ללא ביצוע עסקאות. סטאפים מזוהים בחוקים ניסיוניים. ניתוח חזותי יופיע רק אם הוגדר מפתח OPENAI_API_KEY; הסיווג המספרי נשאר עצמאי.</p>'''+''.join(cards)+'</main></html>'
    (OUT/"report.html").write_text(document,encoding="utf-8")

def main():
    OUT.mkdir(exist_ok=True)
    (OUT/"charts").mkdir(exist_ok=True)
    symbols=[s.strip().upper() for s in (ROOT/"watchlist.txt").read_text().splitlines() if s.strip() and not s.startswith("#")]
    results=[]
    for s in symbols:
        try:
            d=indicators(fetch(s))
            expected=os.getenv("EXPECTED_SESSION_DATE","").strip()
            if expected and str(d.iloc[-1].date)!=expected:
                raise ValueError("Stale latest daily candle: expected "+expected+
                                 ", got "+str(d.iloc[-1].date))
            a=analyze(d)
            levels=structure(d)
            outlook=scenario(d,levels)
            chart(d,s,OUT/"charts"/f"{s}.png",a["active"],levels)
            checklist=build_checklist(d,a)
            visual=review_chart(s,OUT/"charts"/f"{s}.png",{"analysis":a,"checklist":checklist,"levels":levels,"next_session_outlook":outlook})
            results.append({"symbol":s,"analysis":a,"checklist":checklist,"levels":levels,"outlook":outlook,"ai_review":visual})
            print(f"{s}: {a['symbol_date']} {a['active']['status'] if a['active'] else 'NO ACTIVE SETUP'}")
        except Exception as e:
            results.append({"symbol":s,"error":str(e)})
            print(f"{s}: ERROR {e}",flush=True)
    render(results)
    errors=[x["symbol"] for x in results if "error" in x]
    if errors:
        print("REPORT_INCOMPLETE tickers:",", ".join(errors),flush=True)
    (OUT/"results.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Report:",OUT/"report.html")
    if errors: raise SystemExit("Report incomplete; one or more ticker downloads failed")

if __name__=="__main__":main()
