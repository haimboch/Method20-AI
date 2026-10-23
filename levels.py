"""METHOD 20 price levels and conditional next-session scenarios.

Deterministic, backward-looking heuristic; NOT a probabilistic forecast.
All calculations use completed OHLCV bars, SMA20 and volume.
"""
import math
import numpy as np
from signals import candle_pattern

def structure(d, lookback=90, pivot_span=2):
    if len(d)<25:
        raise ValueError("Need 25 completed sessions")
    view=d.tail(lookback).reset_index(drop=True)
    close=float(view.close.iloc[-1])
    # Use confirmed swings; last two sessions cannot be pivots until future bars exist.
    candidates=[]
    for i in range(pivot_span,len(view)-pivot_span):
        hi=float(view.high.iloc[i])
        lo=float(view.low.iloc[i])
        highs=view.high.iloc[i-pivot_span:i+pivot_span+1]
        lows=view.low.iloc[i-pivot_span:i+pivot_span+1]
        if hi==float(highs.max()) and (highs==hi).sum()==1:
            candidates.append(("R",hi,i))
        if lo==float(lows.min()) and (lows==lo).sum()==1:
            candidates.append(("S",lo,i))
    # Merge nearby swing levels into zones. Do not manufacture levels.
    def zones(kind):
        values=sorted([x for x in candidates if x[0]==kind],key=lambda x:x[1],reverse=True)
        groups=[]
        tolerance=max(close*0.008,0.01)
        for _,price,i in values:
            found=next((g for g in groups if abs(price-g["price"])<=tolerance),None)
            if found:
                n=found["touches"]
                found["price"]=(found["price"]*n+price)/(n+1)
                found["touches"]+=1
                found["last_index"]=max(i,found["last_index"])
            else:
                groups.append({"price":price,"touches":1,"last_index":i})
        return groups
    # Reclassify each historical turning level relative to CURRENT close:
    # former resistance can become support and vice versa.
    allzones=zones("S")+zones("R")
    support=sorted((z for z in allzones if z["price"]<close),
                   key=lambda z:close-z["price"])
    resistance=sorted((z for z in allzones if z["price"]>close),
                      key=lambda z:z["price"]-close)
    def output(items):
        selected=[]
        for x in items:
            if any(abs(x["price"]-p["price"])<max(.01,close*.008) for p in selected):
                continue
            selected.append(x)
            if len(selected)==2: break
        return [{"price":round(z["price"],4),"touches":z["touches"]} for z in selected]
    return {"support":output(support),"resistance":output(resistance),
            "price":close,"lookback":len(view),"pivot_span":pivot_span,
            "zone_merge_pct":0.8}

def scenario(d, levels):
    """Qualitative conditional outlook for next completed trading day."""
    x=d.iloc[-1]
    close=float(x.close)
    weekly=float((close/d.close.iloc[-6]-1)*100)
    weekly_label="עולה" if weekly>1 else ("יורדת" if weekly< -1 else "צידית")
    body=abs(float(x.close-x.open))
    span=max(float(x.high-x.low),1e-8)
    green=x.close>x.open
    red=x.close<x.open
    upper=float(x.high-max(x.open,x.close))/span
    lower=float(min(x.open,x.close)-x.low)/span
    pattern=candle_pattern(d,len(d)-1) or ("נר עולה" if green else "נר יורד" if red else "דוג'י")
    avg=float(d.volume.iloc[-21:-1].mean())
    vol_ratio=float(x.volume/avg) if avg>0 else None
    vol_label=("גבוה" if vol_ratio>=1.25 else "נמוך" if vol_ratio<0.8 else "רגיל") if vol_ratio is not None else "לא ידוע"
    # Confidence is deliberately NOT a numerical probability.
    score=(1 if weekly>1 else -1 if weekly< -1 else 0)
    score+=(1 if green and body/span>=.25 else -1 if red and body/span>=.25 else 0)
    if vol_ratio is not None and vol_ratio>=1.25:
        score+=(1 if green else -1 if red else 0)
    if float(x.close)>float(x.sma20):score+=1
    elif float(x.close)<float(x.sma20):score-=1
    bias="נטייה שורית" if score>=2 else "נטייה דובית" if score<=-2 else "מעורב / ללא הכרעה"
    support=levels["support"][0]["price"] if levels["support"] else None
    resist=levels["resistance"][0]["price"] if levels["resistance"] else None
    bullish=(f"פריצה מעל התנגדות ${resist:.2f} עשויה לתמוך בהמשך עלייה" if resist is not None else
             f"מעבר מעל גבוה הנר האחרון ${float(x.high):.2f} הוא סימן שורי לבדיקה")
    bearish=(f"שבירה מתחת לתמיכה ${support:.2f} עשויה להצביע על חולשה" if support is not None else
             f"ירידה מתחת לנמוך הנר האחרון ${float(x.low):.2f} היא סימן חולשה לבדיקה")
    reason=(f"מגמה שבועית {weekly_label} ({weekly:+.2f}%), נר אחרון מסוג {pattern}, "
            f"נפח {vol_label} ({vol_ratio:.2f}x מהממוצע)" if vol_ratio is not None
            else f"מגמה שבועית {weekly_label}, נר אחרון {pattern}, נפח לא ידוע")
    return {"bias":bias,"weekly_trend":weekly_label,"weekly_change_pct":round(weekly,2),
            "last_candle":pattern,"volume_label":vol_label,
            "volume_ratio":round(vol_ratio,2) if vol_ratio is not None else None,
            "bull_case":bullish,"bear_case":bearish,"reason":reason,
            "high":float(x.high),"low":float(x.low),
            "note":"תרחישים מותנים ליום המסחר הבא, לא חיזוי ודאי או הסתברויות מכוילות."}
