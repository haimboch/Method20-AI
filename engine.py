import os, json, time, html
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.ticker import FormatStrFormatter

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

from signals import analyze, classify, candle_pattern, transition, sma20_context, visual_reversal
from checklist import build_checklist
from levels import structure, scenario
from report_format import fmt2, fmt_signed, format_numbers_in_text
from report_sections import grouped_results, section_key, signal_for_display, signal_explanation

from bullish_patterns import PATTERNS
PATTERN_LABELS={**PATTERNS,"DOJI":"Doji","HAMMER":"Hammer","BULLISH_REJECTION":"Bullish Rejection"}

def visible_bullish_patterns(d):
    """Only annotate confirmed shape formations around/below SMA20."""
    view=d.tail(95).reset_index(drop=True)
    first=max(0,len(view)-10)
    selected=[]
    for i in range(first,len(view)):
        reversal=visual_reversal(view,i)
        if not reversal: continue
        name,start,end=reversal
        if start<first: continue
        low=float(view.low.iloc[start:end+1].min())
        high=float(view.high.iloc[start:end+1].max())
        candidate={"pattern":name,"start":start,"end":end,
                   "start_date":str(view.iloc[start].date),
                   "end_date":str(view.iloc[end].date),
                   "low":low,"high":high}
        if selected and start<=selected[-1]["end"]:
            old=selected[-1]
            if end-start>old["end"]-old["start"]:
                selected[-1]=candidate
        else:
            selected.append(candidate)
    return selected

def reversal_for_chart(analysis,view):
    if not analysis:
        return None
    signal=analysis.get("active") or analysis.get("last_event")
    if signal and signal.get("status") not in ("READY","TRIGGERED"):
        return None
    if not signal:
        return None
    dates={str(v):i for i,v in enumerate(view.date)}
    index=dates.get(str(signal.get("signal_date")))
    return (index,signal) if index is not None else None


def chart(d,symbol,path,a,levels=None):
    d=d.tail(95).reset_index(drop=True)
    fig,(ax,vax,cax)=plt.subplots(3,1,figsize=(15,10),sharex=True,gridspec_kw={"height_ratios":[6,1.5,1.8]})
    for i,x in d.iterrows():
        color="#12805c" if x.close>=x.open else "#c44747"
        ax.vlines(i,x.low,x.high,color=color,lw=1)
        ax.add_patch(Rectangle((i-.33,min(x.open,x.close)),.66,max(abs(x.close-x.open),.001),color=color))
        vax.bar(i,x.volume,color=color,width=.75)
    ax.plot(np.arange(len(d)),d.sma20,color="#e5a522",lw=2.2,label="SMA20")
    if levels:
        for z in levels["support"]:
            ax.axhspan(z["low"],z["high"],color="#16815c",alpha=0.20,label="Support zone")
        for z in levels["resistance"]:
            ax.axhspan(z["low"],z["high"],color="#b75a4c",alpha=0.20,label="Resistance zone")
    ax.yaxis.set_major_formatter(FormatStrFormatter("%.2f"))
    cax.yaxis.set_major_formatter(FormatStrFormatter("%.2f"))
    ax.tick_params(axis="both",labelsize=11)
    vax.tick_params(axis="both",labelsize=10)
    cax.tick_params(axis="both",labelsize=10)
    ax.set_title(symbol+"  |  1D  |  "+str(d.iloc[-1].date),fontsize=16)
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
    fig.savefig(path,dpi=175)
    plt.close(fig)

def render(results):
    cards=[]
    groups=grouped_results(results)
    ordered=[r for _,_,items in groups for r in items]
    title_by_key={key:title for key,title,_ in groups}
    count_by_key={key:len(items) for key,_,items in groups}
    previous_group=None
    for r in ordered:
        group=section_key(r)
        if group!=previous_group:
            cards.append('<h2 style="margin:28px 0 6px">'+html.escape(title_by_key[group])
                         +' ('+str(count_by_key[group])+')</h2>')
            previous_group=group
        sym=html.escape(r["symbol"])
        if "error" in r:
            cards.append(f'<section><h2>{sym}</h2><p class="err">נתונים לא זמינים: {html.escape(r["error"])}</p></section>')
            continue
        a=r["analysis"]
        active=a["active"]
        status=a["status"]
        setup=(active or (a.get("last_event") if status=="TRIGGERED" else None) or {}).get("setup","אין סטאפ פעיל")
        old=a["last_event"]
        prior=(f'אירוע קודם: {html.escape(old["status"])} בתאריך {html.escape(old.get("event_date",""))}' if old else "אין אירוע קודם")
        checkrows=''.join('<tr><td>'+html.escape(str(k))+'</td><td>'+html.escape(format_numbers_in_text(v))+'</td></tr>' for k,v,_ in r.get('checklist',[]))
        lv=r.get("levels",{})
        outlook=r.get("outlook",{})
        patterns=r.get("bullish_patterns",[])
        signal=signal_for_display(r)
        signal_box=""
        if signal:
            why=html.escape(signal_explanation(signal))
            phase="ממתין לפריצה" if status=="READY" else "הטריגר נפרץ; הסטאפ עדיין לא נשבר"
            entry=fmt2(signal["high"])
            stop=fmt2(signal["low"])
            signal_box=('<div class="panel"><h3>פירוט סטאפ METHOD 20</h3><p>'
                        +why+'</p><p><b>סטטוס:</b> '+phase
                        +' | <b>תאריך איתות:</b> '+html.escape(str(signal["signal_date"]))
                        +'</p><p><b>טריגר מעל:</b> '+entry
                        +' | <b>סטופ טכני מתחת:</b> '+stop
                        +'</p><small>רמות מחושבות, לא הוראות מסחר בפועל.</small></div>')
        def fmtlevels(values):
            return ", ".join("$"+fmt2(v["low"])+"–$"+fmt2(v["high"]) for v in values) if values else "אין אזור מאומת בחלון הסריקה"
        support_text=html.escape(fmtlevels(lv.get("support",[])))
        resistance_text=html.escape(fmtlevels(lv.get("resistance",[])))
        bias_text=html.escape(outlook.get("bias","לא זמין"))
        reasons=html.escape(format_numbers_in_text(outlook.get("reason","")))
        bull=html.escape(format_numbers_in_text(outlook.get("bull_case","")))
        bear=html.escape(format_numbers_in_text(outlook.get("bear_case","")))

        cards.append(f'<section><h2>{sym} <small>{html.escape(status)}</small></h2><p>תאריך נר אחרון: {html.escape(a["symbol_date"])}</p><p>סגירה: ${a["close"]:.2f} | SMA20: ${a["sma20"]:.2f} | CCI14: {fmt2(a["cci14"])} | Volume / Avg20: {a["volume_ratio"]:.2f}x</p><p>שינוי 5 ימים: {a["change_5d_pct"]:+.2f}% | שינוי 21 ימים: {a["change_21d_pct"]:+.2f}%</p><p>סטאפ: {html.escape(setup)}. {prior}</p>{signal_box}<div class="panel"><h3>תמיכה והתנגדות</h3><p>תמיכות: {support_text}</p><p>התנגדויות: {resistance_text}</p><h3>תרחיש ליום הבא: {bias_text}</h3><p>{reasons}</p><p>תרחיש שורי: {bull}</p><p>תרחיש דובי: {bear}</p><small>תרחישים מותנים, לא תחזית הסתברותית מאומתת.</small></div><p><b>תבניות/נרות היפוך בקרבת SMA20 או מתחתיו (10 אחרונים):</b> {len(patterns)} (ללא סימונים מיוחדים על הגרף)</p><div class="panel"><h3>צ׳קליסט METHOD 20</h3><table>{checkrows}</table></div><img class="chart" src="charts/{sym}.png" alt="Daily chart for {sym}" loading="lazy"/></section>')
    document='''<!doctype html><html lang="he" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>METHOD 20</title><style>body{font-family:Arial,sans-serif;background:#f3f5f9;color:#172331;margin:0;padding:20px}main{max-width:1350px;margin:auto}section{background:white;padding:20px;margin:18px 0;border-radius:16px;box-shadow:0 1px 7px #0001}img{width:100%;max-width:100%;height:auto;display:block;margin:12px auto}small{font-size:14px;color:#666}.panel{background:#f5f7fa;padding:12px;border-radius:10px;margin:12px 0}table{width:100%;border-collapse:collapse}td{padding:8px;border-bottom:1px solid #ddd}td:first-child{font-weight:bold}.err{color:#aa3333}p{line-height:1.65}</style><main><h1>METHOD 20 AI | דוח פיילוט</h1><p>מידע למחקר בלבד. ללא ביצוע עסקאות. סטאפים מזוהים בחוקים ניסיוניים. כל הניתוחים מחושבים על פי נתוני מסחר באמצעות Python, ללא סקירת תמונה באמצעות OpenAI.</p>'''+''.join(cards)+'</main></html>'
    (OUT/"report.html").write_text(document,encoding="utf-8")

def main():
    OUT.mkdir(exist_ok=True)
    (OUT/"charts").mkdir(exist_ok=True)
    symbols=[s.strip().upper() for s in (ROOT/"watchlist.txt").read_text().splitlines() if s.strip() and not s.startswith("#")]
    if len(symbols)!=len(set(symbols)):
        raise ValueError("watchlist.txt contains duplicate symbols")
    if not 1<=len(symbols)<=40:
        raise ValueError("Watchlist size must stay between 1 and 40 tickers")
    print(f"WATCHLIST_COUNT={len(symbols)}",flush=True)
    results=[]
    # Conservative shared request pacing for vendor plans with low RPM limits.
    # No local machine or extra secrets required.
    request_interval=float(os.getenv("MASSIVE_REQUEST_INTERVAL_SEC","20"))
    next_request_at=0.0
    for s in symbols:
        try:
            remaining=next_request_at-time.monotonic()
            if remaining>0:
                print(f"DATA_RATE_LIMIT_PACING ticker={s} sleep_seconds={remaining:.1f}",flush=True)
                time.sleep(remaining)
            next_request_at=time.monotonic()+request_interval
            d=indicators(fetch(s))
            expected=os.getenv("EXPECTED_SESSION_DATE","").strip()
            if expected and str(d.iloc[-1].date)!=expected:
                raise ValueError("Stale latest daily candle: expected "+expected+
                                 ", got "+str(d.iloc[-1].date))
            a=analyze(d)
            levels=structure(d,lookback=95)
            outlook=scenario(d,levels)
            chart(d,s,OUT/"charts"/f"{s}.png",a,levels)
            checklist=build_checklist(d,a)
            patterns=visible_bullish_patterns(d)
            results.append({"symbol":s,"analysis":a,"checklist":checklist,
                            "levels":levels,"outlook":outlook,
                            "bullish_patterns":patterns})
            print(f"{s}: {a['symbol_date']} {a['active']['status'] if a['active'] else 'NO ACTIVE SETUP'}")
        except Exception as e:
            results.append({"symbol":s,"error":str(e)})
            print(f"{s}: ERROR type={type(e).__name__} detail={e}",flush=True)
    render(results)
    errors=[x["symbol"] for x in results if "error" in x]
    if errors:
        print("REPORT_INCOMPLETE tickers:",", ".join(errors),flush=True)
    (OUT/"results.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    session_date=os.getenv("EXPECTED_SESSION_DATE","").strip() or str(
        next(x["analysis"]["symbol_date"] for x in results if "analysis" in x))
    health={"session_date":session_date,
            "symbols":[r["symbol"] for r in results],
            "expected_ticker_count":len(symbols),
            "analyzed_ticker_count":len(results)-len(errors),
            "ai_complete_count":0,
            "visual_ai_enabled":False,
            "ready_count":sum(r.get("analysis",{}).get("status")=="READY" for r in results),
            "triggered_count":sum(r.get("analysis",{}).get("status")=="TRIGGERED" for r in results),
            "failed_symbols":errors,
            "failure_details":{r["symbol"]:r["error"] for r in results if "error" in r},
            "complete":not errors}
    (OUT/"metadata.json").write_text(
        json.dumps(health,ensure_ascii=False,indent=2),encoding="utf-8")
    print("REPORT_HEALTH",json.dumps(health,ensure_ascii=False),flush=True)
    print("Report:",OUT/"report.html")
    if errors: raise SystemExit("Report incomplete; one or more ticker downloads failed")

if __name__=="__main__":main()
