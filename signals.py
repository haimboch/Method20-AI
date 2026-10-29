"""METHOD 20 deterministic signals (prototype). No brokerage actions."""
import math
import pandas as pd

def candle_pattern(d, i):
    """Return candlestick label or None. Doji alone is neutral, not a LONG reversal."""
    x = d.iloc[i]
    o, h, l, c = (float(x[k]) for k in ("open", "high", "low", "close"))
    rng = h-l
    if rng <= 0: return None
    body = abs(c-o)
    top = h-max(o,c)
    bottom = min(o,c)-l
    green = c>o
    if i>0:
        p=d.iloc[i-1]
        if (green and p.close<p.open and o<=p.close and c>=p.open
                and body>0 and abs(p.close-p.open)>0):
            return "BULLISH_ENGULFING"
    if bottom>=2*max(body, rng*0.03) and top<=max(body,rng*0.20) and min(o,c)>l:
        return "HAMMER"
    if green and (c-l)/rng>=0.65 and body/rng>=0.25:
        return "BULLISH_REJECTION"
    return None

def sma20_context(d,i):
    """Below SMA20 or testing it as support; no marks far above the average."""
    if i<0 or i>=len(d): return False
    x=d.iloc[i]
    if pd.isna(x.sma20) or x.sma20<=0: return False
    avg=float(x.sma20)
    close=float(x.close)
    low=float(x.low)
    return close<avg or (low<=avg*1.005 and avg*.98<=close<=avg*1.025)

def visual_reversal(d,i):
    """Single candle rejection/hammer/doji or completed 2-3 bullish formation."""
    from bullish_patterns import detect
    if not sma20_context(d,i): return None
    formations=detect(d.iloc[:i+1],last_n=3)
    match=next((p for p in reversed(formations) if p["end"]==i),None)
    if match: return match["pattern"],match["start"],i
    x=d.iloc[i]
    rng=float(x.high-x.low)
    if rng<=0: return None
    body=abs(float(x.close-x.open))
    if body/rng<=.10: return "DOJI",i,i
    shape=candle_pattern(d,i)
    if shape in ("HAMMER","BULLISH_REJECTION"):
        return shape,i,i
    return None

def cci_upturn(d, i):
    if i<2: return False
    values=[d.iloc[j].cci for j in (i-2,i-1,i)]
    return all(pd.notna(v) for v in values) and values[2]>values[1] and values[1]<=values[0]

def classify(d,i):
    """A: CCI was <-100 in last five sessions; B: no oversold requirement.
    Volume must be higher than previous day OR the previous 20-day average.
    These parameter thresholds remain provisional until strategy validation.
    """
    if i<21: return None
    cur,prev=d.iloc[i],d.iloc[i-1]
    required=(cur.sma20,cur.cci,prev.cci,cur.volume,prev.volume,cur.vol20)
    if any(pd.isna(v) for v in required): return None
    reversal=visual_reversal(d,i)
    if not reversal or not cci_upturn(d,i): return None
    pattern=reversal[0]
    # Today's volume does not contribute to the threshold, avoiding self-reference.
    avg_prior_volume=d.volume.iloc[i-20:i].mean()
    volume_ok=bool(cur.volume>prev.volume or cur.volume>avg_prior_volume)
    if not volume_ok: return None
    recent_down=i>=10 and d.close.iloc[i-5]<d.close.iloc[i-10]
    below=cur.close<cur.sma20
    near=abs(cur.low/cur.sma20-1)<=0.025 and cur.close>=cur.sma20*0.98
    oversold=bool((d.cci.iloc[max(0,i-5):i+1]<-100).any())
    if below and recent_down and oversold:
        setup="A: MEAN_REVERSION"
    elif near:
        setup="B: SMA20_BOUNCE"
    else: return None
    return {"setup":setup,"pattern":pattern,"signal_date":str(cur.date),
            "high":float(d.high.iloc[reversal[1]:i+1].max()),
            "low":float(d.low.iloc[reversal[1]:i+1].min()),"status":"READY",
            "cci14":float(cur.cci),"volume_ratio":float(cur.volume/avg_prior_volume)}

def transition(signal, day, date=None):
    """Only a subsequent session may cross a reversal boundary."""
    if signal is None: return None
    state=signal.get("status")
    if state not in ("READY","TRIGGERED"): return signal
    if str(date if date is not None else day.date)<=str(signal["signal_date"]):
        return signal
    if state=="TRIGGERED":
        if float(day.low)<float(signal["low"]):
            updated=dict(signal)
            updated["status"]="BROKEN"
            updated["event_date"]=str(date if date is not None else day.date)
            updated["broken_date"]=updated["event_date"]
            return updated
        return signal
    high_cross=bool(day.high>signal["high"])
    low_cross=bool(day.low<signal["low"])
    if not (high_cross or low_cross): return signal
    updated=dict(signal)
    updated["status"]=("AMBIGUOUS" if high_cross and low_cross
                       else "TRIGGERED" if high_cross else "INVALIDATED")
    updated["event_date"]=str(date if date is not None else day.date)
    return updated

def analyze(d):
    if len(d)<22: raise ValueError("Not enough daily bars for analysis")
    active=None
    last_event=None
    # Warm-up: enough history for CCI, SMA20 and weekly trend.
    for i in range(21,len(d)):
        day=d.iloc[i]
        if last_event and last_event.get("status")=="TRIGGERED":
            last_event=transition(last_event,day)
            continue
        if active:
            updated=transition(active,day)
            if updated["status"]!="READY":
                last_event=updated
                active=None
            else:
                active=updated
            continue
        signal=classify(d,i)
        if signal: active=signal
    x=d.iloc[-1]
    if active: status="READY"
    elif last_event and (last_event.get("status")=="TRIGGERED"
                         or last_event.get("event_date")==str(x.date)):
        status=last_event["status"]
    else: status="NO ACTIVE SETUP"
    def num(v): return float(v) if pd.notna(v) and math.isfinite(float(v)) else None
    return {"symbol_date":str(x.date),"close":num(x.close),"sma20":num(x.sma20),
            "cci14":num(x.cci),"volume_ratio":num(x.volume/x.vol20),
            "change_5d_pct":num((x.close/d.close.iloc[-6]-1)*100),
            "change_21d_pct":num((x.close/d.close.iloc[-22]-1)*100),
            "status":status,"active":active,"last_event":last_event}
