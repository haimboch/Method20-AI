"""Persistent zones, scored from daily swings and normalized volume."""
from datetime import datetime
import math
import pandas as pd

WEIGHTS={"touches":.35,"volume":.25,"proximity":.25,"recency":.15}
def atr14(d):
    previous=d.close.shift(1)
    tr=pd.concat([(d.high-d.low),(d.high-previous).abs(),
                  (d.low-previous).abs()],axis=1).max(axis=1)
    return float(tr.tail(14).mean())

def _pivots(d,kind,atr):
    result=[]
    for i in range(2,len(d)-2):
        x=d.iloc[i]
        values=d.low if kind=="support" else d.high
        area=values.iloc[i-2:i+3]
        if (kind=="support" and x.low>area.min()) or (kind=="resistance" and x.high<area.max()):
            continue
        reaction=(float(d.high.iloc[i+1:i+3].max()-x.low) if kind=="support"
                  else float(x.high-d.low.iloc[i+1:i+3].min()))
        if reaction<.75*atr:continue
        avg=float(d.volume.iloc[max(0,i-20):i].mean())
        ratio=float(d.volume.iloc[i:i+3].max()/avg) if avg>0 else 0
        result.append({"i":i,"price":float(x.low if kind=="support" else x.high),
                       "volume_ratio":min(ratio,3.0),"date":str(x.date)})
    return result

def candidates(d,kind,reference):
    view=d.tail(95).reset_index(drop=True)
    if len(view)<30:return []
    atr=atr14(view)
    if not math.isfinite(atr) or atr<=0:return []
    pivots=_pivots(view,kind,atr)
    clusters=[]
    for p in pivots:
        group=next((g for g in clusters if abs(p["price"]-sum(t["price"] for t in g)/len(g))<=.5*atr),None)
        if group is None:clusters.append([p])
        else:group.append(p)
    result=[]
    for points in clusters:
        points=sorted(points,key=lambda p:p["i"])
        independent=[]
        for p in points:
            if independent:
                last=independent[-1]
                if p["i"]-last["i"]<3:continue
                between=view.iloc[last["i"]:p["i"]+1]
                move=(float(between.high.max()-min(last["price"],p["price"])) if kind=="support"
                      else float(max(last["price"],p["price"])-between.low.min()))
                if move<.75*atr:continue
            independent.append(p)
        if len(independent)<2:continue
        if sum(p["volume_ratio"]>=1 for p in independent)<1:continue
        if any(p["volume_ratio"]<.65 for p in independent):continue
        prices=[p["price"] for p in independent]
        low=min(prices)-.08*atr;high=max(prices)+.08*atr
        if kind=="support" and high>=reference:continue
        if kind=="resistance" and low<=reference:continue
        center=(low+high)/2
        distance=abs(center-reference)/max(atr,1e-6)
        touches=min(len(independent)/5,1)
        vol=min(sum(p["volume_ratio"] for p in independent)/len(independent)/2,1)
        proximity=1/(1+distance)
        recency=independent[-1]["i"]/len(view)
        score=100*(.35*touches+.25*vol+.25*proximity+.15*recency)
        if kind=="support" and low<=float(view.sma20.iloc[-1])<=high:
            score+=min(10,10*.75)
        result.append({"kind":kind,"low":round(low,4),"high":round(high,4),
                       "score":round(score,2),"touches":len(independent),
                       "created_at":str(view.date.iloc[-1]),"status":"ACTIVE",
                       "history":[p["date"] for p in independent]})
    return sorted(result,key=lambda z:z["score"],reverse=True)

def falling(d):
    if len(d)<12:return False
    # Falling last five sessions, or lower highs during a pullback.
    segment=d.tail(6)
    return bool(segment.close.iloc[-1]<segment.close.iloc[0] and
                (segment.high.iloc[-1]<segment.high.iloc[0] or
                 segment.close.iloc[-1]<d.sma20.iloc[-1]))

def _broken(zone,kind,closes):
    if len(closes)<2:return False
    return (all(v<float(zone["low"]) for v in closes) if kind=="support"
            else all(v>float(zone["high"]) for v in closes))

def _retest(d,zone,kind):
    if len(d)<22:return False
    atr=atr14(d)
    x=d.iloc[-1]
    avg=float(d.volume.iloc[-21:-1].mean())
    if not math.isfinite(atr) or atr<=0 or avg<=0 or x.volume<avg:
        return False
    if kind=="resistance": # old resistance retested as support
        touched=zone["low"]<=x.low<=zone["high"] and x.close>zone["high"]
        reaction=float(x.close-x.low)
    else: # old support retested as resistance
        touched=zone["low"]<=x.high<=zone["high"] and x.close<zone["low"]
        reaction=float(x.high-x.close)
    return bool(touched and reaction>=.75*atr)

def update_book(d,book,display_kind=None,reference=None):
    """Fixed price bands; persist and validate even while hidden.

    Existing locks are not replaced just because another candidate scores
    better. Historical bands survive the 95-candle viewing window.
    """
    book=dict(book or {})
    today=str(d.date.iloc[-1])
    closes=list(map(float,d.close.tail(2)))
    history=list(book.get("archived",[]))
    def validate(zone,kind):
        if zone is None:return None
        z=dict(zone)
        status=z.get("status","HIDDEN")
        if status in ("ACTIVE","HIDDEN") and _broken(z,kind,closes):
            z["status"]="WAITING_RETEST"
            z["break_date"]=today
        elif status=="WAITING_RETEST" and today>z.get("break_date",today):
            if _retest(d,z,kind):
                z["status"]="ROLE_REVERSED"
                z["retest_date"]=today
        return z
    for kind in ("support","resistance"):
        book[kind]=validate(book.get(kind),kind)
    history=[validate(z,z["kind"]) for z in history]
    # Restore confirmed role reversals only when no active zone already
    # occupies the destination type, respecting its original fixed edges.
    for src in ("support","resistance"):
        z=book.get(src)
        if z and z.get("status")=="ROLE_REVERSED":
            dst="resistance" if src=="support" else "support"
            existing=book.get(dst)
            if existing is None or existing.get("status") not in ("ACTIVE","HIDDEN"):
                book[dst]={**z,"kind":dst,"status":"HIDDEN",
                           "created_at":z.get("retest_date",today)}
    for z in history:
        if z.get("status")=="ROLE_REVERSED":
            dst="resistance" if z["kind"]=="support" else "support"
            existing=book.get(dst)
            if existing is None or existing.get("status") not in ("ACTIVE","HIDDEN"):
                book[dst]={**z,"kind":dst,"status":"HIDDEN",
                           "created_at":z.get("retest_date",today)}
    for kind in ("support","resistance"):
        z=book.get(kind)
        if z and z.get("status") in ("ACTIVE","HIDDEN"):
            z["status"]="HIDDEN"
    if display_kind in ("support","resistance") and reference is not None:
        kind=display_kind
        z=book.get(kind)
        valid=lambda q: (q is not None and q.get("status") in ("ACTIVE","HIDDEN")
                         and zone_is_relevant(q,kind,float(reference)))
        if z and z.get("status") in ("ACTIVE","HIDDEN"):
            # Retain this specific lock even when it is temporarily on
            # the wrong side. It can become visible again without replacement.
            if valid(z):
                z["status"]="ACTIVE"
        else:
            # Replace a confirmed broken zone; archive its previous evidence.
            if z:
                if not any(q.get("kind")==kind and q.get("created_at")==z.get("created_at")
                           and q.get("low")==z.get("low") for q in history):
                    history.append(dict(z))
            found=next((dict(q) for q in reversed(history) if q["kind"]==kind
                        and valid(q)),None)
            if found is None:
                choices=candidates(d,kind,float(reference))
                found=choices[0] if choices else None
            if found is not None:
                book[kind]={**found,"status":"ACTIVE"}
            elif z:
                book[kind]=None
    book["archived"]=history
    return book

def chosen_zone(book,kind):
    zone=(book or {}).get(kind)
    return zone if zone and zone.get("status")=="ACTIVE" else None

def zone_is_relevant(zone,kind,reference):
    if not zone or reference is None:return False
    return (zone["high"]<reference if kind=="support" else zone["low"]>reference)

def risk_reward(signal,zone):
    if not signal or not zone:return None
    entry=float(signal["high"]);stop=float(signal["low"])
    if entry<=stop:return None
    return round((float(zone["low"])-entry)/(entry-stop),2)
