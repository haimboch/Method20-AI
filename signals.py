"""METHOD 20 daily long-only candidate and confirmed setup lifecycle."""
import math
import pandas as pd
from patterns_method20 import detect_at

def cci_upturn(d,i):
    if i<2:return False
    values=[d.iloc[j].cci for j in (i-2,i-1,i)]
    return all(pd.notna(v) for v in values) and values[2]>values[1] and values[1]<=values[0]

def candle_pattern(d,i):
    p=detect_at(d,i)
    return p["pattern"] if p and p["end"]==p["start"] else None

def sma20_context(d,i):
    if i<10 or pd.isna(d.iloc[i].sma20):return False
    return bool(d.iloc[i].close<d.iloc[i].sma20 or
                (d.iloc[i].low<=d.iloc[i].sma20*1.02 and
                 d.iloc[i].close>=d.iloc[i].sma20*.98))

def setup_context(d,i):
    if i<25:return None
    x=d.iloc[i]
    sma=float(x.sma20)
    if not math.isfinite(sma) or sma<=0:return None
    down=bool(d.close.iloc[i-5]<d.close.iloc[i-10] or
              d.close.iloc[i-1]<d.close.iloc[i-5])
    if x.close<sma and down:
        return "A: MEAN_REVERSION"
    # Recent pullback following an established upward SMA20 slope.
    prior_up=bool(d.sma20.iloc[i-5]>d.sma20.iloc[i-10])
    pullback=bool(d.close.iloc[i-1]<d.close.iloc[i-5])
    near=bool(x.low<=sma*1.02 and x.close>=sma*.98)
    if prior_up and pullback and near:
        return "B: SMA20_BOUNCE"
    return None

def visual_reversal(d,i):
    if not setup_context(d,i):return None
    p=detect_at(d,i)
    return (p["pattern"],p["start"],i) if p else None

def candidate(d,i):
    context=setup_context(d,i)
    if not context:return None
    shape=detect_at(d,i)
    if not shape:return None
    if context.startswith("A") and not bool((d.cci.iloc[i-5:i+1]<-100).any()):
        # Oversold is a confirmation rule, not a condition for drawing a candidate.
        pass
    return {"setup":context,"pattern":shape["pattern"],
            "signal_date":shape["signal_date"],"signal_index":i,
            "start_date":str(d.iloc[shape["start"]].date),
            "high":shape["high"],"low":shape["low"],
            "status":"CANDIDATE","confirmation_date":None}

def confirmation(d,i,signal):
    if i-signal["signal_index"]>2:return False
    if not cci_upturn(d,i):return False
    x=d.iloc[i]
    avg=d.volume.iloc[i-20:i].mean()
    if pd.isna(avg) or avg<=0:return False
    volume_ok=bool(x.volume>d.volume.iloc[i-1] or x.volume>avg)
    if not volume_ok:return False
    if signal["setup"].startswith("A"):
        if not bool((d.cci.iloc[max(0,signal["signal_index"]-5):i+1]<-100).any()):
            return False
    return True

def classify(d,i):
    s=candidate(d,i)
    if s and confirmation(d,i,s):
        s["status"]="READY";s["confirmation_date"]=str(d.iloc[i].date)
        return s
    return None

def transition(signal,day,date=None):
    """Daily OHLC technical boundaries; execution events remain separate."""
    if signal is None:return None
    status=signal["status"]
    day_date=str(date if date is not None else day.date)
    if day_date<=signal["signal_date"]:return signal
    if status not in ("CANDIDATE","READY","TRIGGERED"):return signal
    updated=dict(signal)
    upper=bool(day.high>signal["high"])
    lower=bool(day.low<signal["low"])
    if status=="TRIGGERED":
        if lower:updated["technical_stop_touched"]=day_date
        return updated
    if upper or lower:
        updated["status"]=("AMBIGUOUS" if upper and lower else
                           "UNCONFIRMED_BREAKOUT" if upper and status=="CANDIDATE" else
                           "TRIGGERED" if upper else "INVALIDATED")
        updated["event_date"]=day_date
    return updated

def analyze(d,closed_signal_dates=()):
    if len(d)<26:raise ValueError("Not enough daily bars for METHOD20")
    closed_dates=set(map(str,closed_signal_dates))
    active=None;last_event=None
    for i in range(25,len(d)):
        day=d.iloc[i];day_date=str(day.date)
        if active and active["signal_date"] in closed_dates:
            last_event=dict(active,status="SKIPPED_OR_CLOSED",event_date=day_date)
            active=None
            continue
        if active:
            active=transition(active,day)
            if active["status"]=="CANDIDATE":
                if confirmation(d,i,active):
                    active=dict(active,status="READY",confirmation_date=day_date)
                elif i-active["signal_index"]>=2:
                    active=dict(active,status="EXPIRED",event_date=day_date)
            if active["status"] not in ("CANDIDATE","READY","TRIGGERED"):
                last_event=active;active=None
            continue
        new=candidate(d,i)
        if new:
            if confirmation(d,i,new):
                new["status"]="READY";new["confirmation_date"]=day_date
            active=new
    x=d.iloc[-1]
    status=active["status"] if active else (
        last_event["status"] if last_event and last_event.get("event_date")==str(x.date)
        else "NO ACTIVE SETUP")
    def number(v):
        return float(v) if pd.notna(v) and math.isfinite(float(v)) else None
    return {"symbol_date":str(x.date),"close":number(x.close),
            "sma20":number(x.sma20),"cci14":number(x.cci),
            "volume_ratio":number(x.volume/x.vol20),
            "change_5d_pct":number((x.close/d.close.iloc[-6]-1)*100),
            "change_21d_pct":number((x.close/d.close.iloc[-22]-1)*100),
            "status":status,"active":active,"last_event":last_event}
