"""Bullish reversal-pattern recognition for METHOD20.

A shape is *not* a buy: location, CCI, volume and subsequent breakout are
checked by signals.py. A bullish reversal requires a preceding price decline.
"""
PATTERN_NAMES=("HAMMER","DOJI","DRAGONFLY_DOJI","BULLISH_BELT_HOLD",
 "BULLISH_ENGULFING","BULLISH_HARAMI","PIERCING_LINE","TWEEZER_BOTTOM",
 "MORNING_STAR","THREE_INSIDE_UP","THREE_OUTSIDE_UP","INVERTED_HAMMER")

def _bar(d,j):
    x=d.iloc[j];o,h,l,c=map(float,(x.open,x.high,x.low,x.close))
    r=max(h-l,1e-9);body=abs(c-o)
    return dict(o=o,h=h,l=l,c=c,r=r,body=body,green=c>o,red=c<o,
                top=h-max(o,c),bottom=min(o,c)-l)

def _decline(d,start):
    """Decline BEFORE the first pattern candle, never using later candles."""
    if start<6:return False
    a=d.close.iloc[start-6:start-3].astype(float).mean()
    b=d.close.iloc[start-3:start].astype(float).mean()
    return bool(b<a and float(d.close.iloc[start-1])<float(d.close.iloc[start-6]))

def detect_at(d,i):
    """Return strongest completed bullish shape, or None.

    Testing a multi-candle shape must not prevent falling back to another
    valid shape when its preceding-decline requirement fails.
    """
    if i<0 or i>=len(d):return None
    b=_bar(d,i)
    def found(name,n):
        start=i-n+1
        if not _decline(d,start):return None
        return {"pattern":name,"start":start,"end":i,
                "signal_date":str(d.iloc[i].date),
                "high":float(d.high.iloc[start:i+1].max()),
                "low":float(d.low.iloc[start:i+1].min())}
    # Prioritize three-, then two-, then one-candle formations.
    if i>=2:
        z,a=_bar(d,i-2),_bar(d,i-1)
        checks=[
          ("MORNING_STAR",z["red"] and z["body"]/z["r"]>=.45
            and a["body"]<z["body"]*.55 and b["green"]
            and b["c"]>(z["o"]+z["c"])/2),
          ("THREE_INSIDE_UP",z["red"] and a["green"]
            and z["c"]<=a["o"]<a["c"]<=z["o"] and b["green"]
            and b["c"]>z["o"]),
          ("THREE_OUTSIDE_UP",z["red"] and a["green"]
            and a["o"]<=z["c"] and a["c"]>=z["o"] and b["green"]
            and b["c"]>a["c"]),
        ]
        for name,match in checks:
            if match:
                result=found(name,3)
                if result:return result
    if i>=1:
        a=_bar(d,i-1)
        checks=[
          ("BULLISH_ENGULFING",a["red"] and b["green"]
           and b["o"]<=a["c"] and b["c"]>=a["o"] and b["body"]>=a["body"]),
          ("BULLISH_HARAMI",a["red"] and b["green"]
           and a["c"]<=b["o"]<b["c"]<=a["o"]
           and b["body"]<a["body"]*.8),
          ("PIERCING_LINE",a["red"] and b["green"] and b["o"]<=a["c"]
           and (a["o"]+a["c"])/2<=b["c"]<a["o"]),
          ("TWEEZER_BOTTOM",a["red"] and b["green"]
           and abs(a["l"]-b["l"])<=max(b["r"]*.15,b["l"]*.003)
           and b["c"]>a["c"]),
        ]
        for name,match in checks:
            if match:
                result=found(name,2)
                if result:return result
    # A Doji is neutral in isolation; the decline+setup context makes it
    # a *candidate* bullish reversal, never confirmation by itself.
    checks=[
      ("DRAGONFLY_DOJI",b["body"]/b["r"]<=.10
       and b["bottom"]/b["r"]>=.60 and b["top"]/b["r"]<=.10),
      ("DOJI",b["body"]/b["r"]<=.10),
      ("HAMMER",b["bottom"]>=2*max(b["body"],b["r"]*.03)
       and b["top"]<=b["r"]*.20 and min(b["o"],b["c"])>=b["l"]+b["r"]*.55),
      ("INVERTED_HAMMER",b["top"]>=2*max(b["body"],b["r"]*.03)
       and b["bottom"]<=b["r"]*.20 and max(b["o"],b["c"])<=b["l"]+b["r"]*.45),
      ("BULLISH_BELT_HOLD",b["green"] and b["body"]/b["r"]>=.65
       and b["bottom"]/b["r"]<=.08 and b["top"]/b["r"]<=.20),
    ]
    for name,match in checks:
        if match:
            result=found(name,1)
            if result:return result
    return None
