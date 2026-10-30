"""12 bullish formations. Returns the best completed pattern at bar i."""
PATTERN_NAMES=("HAMMER","DOJI","DRAGONFLY_DOJI","BULLISH_BELT_HOLD",
 "BULLISH_ENGULFING","BULLISH_HARAMI","PIERCING_LINE","TWEEZER_BOTTOM",
 "MORNING_STAR","THREE_INSIDE_UP","THREE_OUTSIDE_UP","INVERTED_HAMMER")

def detect_at(d,i):
    if i<0:return None
    def bar(j):
        x=d.iloc[j]; o,h,l,c=map(float,(x.open,x.high,x.low,x.close))
        r=max(h-l,1e-9);body=abs(c-o)
        return dict(o=o,h=h,l=l,c=c,r=r,body=body,
                    green=c>o,red=c<o,top=h-max(o,c),bottom=min(o,c)-l)
    b=bar(i)
    def found(name,n):
        start=i-n+1
        return {"pattern":name,"start":start,"end":i,
                "signal_date":str(d.iloc[i].date),
                "high":float(d.high.iloc[start:i+1].max()),
                "low":float(d.low.iloc[start:i+1].min())}
    if i>=2:
        z,a=bar(i-2),bar(i-1)
        if (z["red"] and z["body"]/z["r"]>=.45 and
            a["body"]<z["body"]*.55 and b["green"] and
            b["c"]>(z["o"]+z["c"])/2):
            return found("MORNING_STAR",3)
        if (z["red"] and a["green"] and z["c"]<=a["o"]<a["c"]<=z["o"]
            and b["green"] and b["c"]>z["o"]):
            return found("THREE_INSIDE_UP",3)
        if (z["red"] and a["green"] and a["o"]<=z["c"] and a["c"]>=z["o"]
            and b["green"] and b["c"]>a["c"]):
            return found("THREE_OUTSIDE_UP",3)
    if i>=1:
        a=bar(i-1)
        if a["red"] and b["green"] and b["o"]<=a["c"] and b["c"]>=a["o"]:
            return found("BULLISH_ENGULFING",2)
        if a["red"] and b["green"] and a["c"]<=b["o"]<b["c"]<=a["o"] and b["body"]<a["body"]*.8:
            return found("BULLISH_HARAMI",2)
        if (a["red"] and b["green"] and b["o"]<=a["c"]
            and (a["o"]+a["c"])/2<=b["c"]<a["o"]):
            return found("PIERCING_LINE",2)
        if (a["red"] and b["green"] and
            abs(a["l"]-b["l"])<=max(b["r"]*.15,b["l"]*.003)):
            return found("TWEEZER_BOTTOM",2)
    if b["body"]/b["r"]<=.10:
        if b["bottom"]/b["r"]>=.60 and b["top"]/b["r"]<=.10:
            return found("DRAGONFLY_DOJI",1)
        return found("DOJI",1)
    if (b["bottom"]>=2*max(b["body"],b["r"]*.03) and
        b["top"]<=b["r"]*.20 and min(b["o"],b["c"])>=b["l"]+b["r"]*.55):
        return found("HAMMER",1)
    if (b["top"]>=2*max(b["body"],b["r"]*.03) and
        b["bottom"]<=b["r"]*.20 and max(b["o"],b["c"])<=b["l"]+b["r"]*.45):
        return found("INVERTED_HAMMER",1)
    if (b["green"] and b["body"]/b["r"]>=.65 and
        b["bottom"]/b["r"]<=.08 and b["top"]/b["r"]<=.20):
        return found("BULLISH_BELT_HOLD",1)
    return None
