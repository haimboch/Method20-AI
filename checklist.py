"""Deterministic facts displayed for EVERY stock in the daily HTML report."""
import pandas as pd
from signals import candle_pattern, cci_upturn

def build_checklist(d, a):
    i=len(d)-1
    x=d.iloc[i]
    sma=float(x.sma20)
    price=float(x.close)
    dist=(price/sma-1)*100
    last_pattern=candle_pattern(d,i)
    prev_avg=float(d.volume.iloc[-21:-1].mean())
    ratio=float(x.volume/prev_avg) if prev_avg>0 else None
    down_move=bool(d.close.iloc[-6]<d.close.iloc[-11]) if len(d)>=11 else None
    cci_over=bool((d.cci.iloc[-6:]<-100).any())
    checks=[
        ("מחיר מול SMA20", f"{dist:+.2f}% מהממוצע", "INFO"),
        ("מגמה 5 ימים", f"{a['change_5d_pct']:+.2f}%", "INFO"),
        ("מגמה 21 ימים", f"{a['change_21d_pct']:+.2f}%", "INFO"),
        ("נר אחרון",last_pattern or "לא זוהה נר היפוך שורי","PASS" if last_pattern else "NO"),
        ("נפח ביחס לממוצע 20 קודמים",
         f"{ratio:.2f}x" if ratio is not None else "אין נתון",
         "PASS" if ratio is not None and (x.volume>d.volume.iloc[-2] or ratio>1) else "NO"),
        ("CCI(14) פונה מעלה", "כן" if cci_upturn(d,i) else "לא",
         "PASS" if cci_upturn(d,i) else "NO"),
        ("CCI מתחת 100- לאחרונה", "כן" if cci_over else "לא",
         "PASS" if cci_over else "NO"),
        ("מגמה יורדת לפי חלון קצר", "כן" if down_move else "לא",
         "PASS" if down_move else "NO"),
    ]
    sig=a.get("active")
    if sig:
        checks.extend([
            ("סטאפ פעיל",sig["setup"],"PASS"),
            ("תאריך נר היפוך",sig["signal_date"],"INFO"),
            ("גבוה נר היפוך",f"${sig['high']:.2f}","INFO"),
            ("נמוך נר היפוך",f"${sig['low']:.2f}","INFO"),
        ])
    else:
        checks.append(("סטאפ פעיל","לא זוהה סטאפ פעיל","NO"))
    return checks
