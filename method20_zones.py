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

def update_book(d,book,display_kind=None,reference=None):
    """Do not shift locked boundaries, including while hidden or outside chart."""
    book=dict(book or {})
    closes=[float(v) for v in d.close.tail(2)]
    for kind in ("support","resistance"):
        zone=book.get(kind)
        if not zone:continue
        zone=dict(zone)
        if zone["status"] in ("ACTIVE","HIDDEN"):
            broken=(all(c<zone["low"] for c in closes) if kind=="support"
                    else all(c>zone["high"] for c in closes))
            if broken:
                zone["status"]="WAITING_RETEST"
                zone["break_date"]=str(d.date.iloc[-1])
            elif kind!=display_kind:
                zone["status"]="HIDDEN"
            else:
                zone["status"]="ACTIVE"
        # A broken zone stays historical; role-reversal requires an independent retest.
        if zone["status"]=="WAITING_RETEST" and str(d.date.iloc[-1])>zone["break_date"]:
            atr=atr14(d)
            last=d.iloc[-1]
            if kind=="resistance": # old resistance can become support
                touched=last.low<=zone["high"] and last.close>=zone["high"]
                reaction=last.close-zone["low"]
            else:
                touched=last.high>=zone["low"] and last.close<=zone["low"]
                reaction=zone["high"]-last.close
            avg=d.volume.iloc[-21:-1].mean()
            if touched and reaction>=.75*atr and avg>0 and last.volume>=avg:
                zone["status"]="ROLE_REVERSED"
                other="support" if kind=="resistance" else "resistance"
                if not book.get(other) or book[other].get("status")!="ACTIVE":
                    book[other]={**zone,"kind":other,"status":"HIDDEN",
                                 "created_at":str(last.date)}
        book[kind]=zone
    if display_kind:
        zone=book.get(display_kind)
        eligible=lambda z: (
            z is not None and z.get("status") in ("ACTIVE","HIDDEN")
            and reference is not None
            and (float(z["high"])<float(reference) if display_kind=="support"
                 else float(z["low"])>float(reference)))
        if not eligible(zone):
            if zone and zone.get("status") in ("ACTIVE","HIDDEN"):
                # Historical levels are retained, but never displayed on the
                # wrong side of the current price/trigger.
                zone["status"]="HIDDEN"
                book.setdefault("archived",[]).append(dict(zone))
            zone=None
            for old in reversed(book.get("archived",[])):
                if old.get("kind")==display_kind and eligible(old):
                    zone=dict(old)
                    break
            if zone is None:
                choices=candidates(d,display_kind,reference)
                zone=choices[0] if choices else None
            if zone is not None:
                book[display_kind]=zone
        if zone is not None and eligible(zone):
            zone["status"]="ACTIVE"
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
