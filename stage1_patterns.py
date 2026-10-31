"""METHOD20 stage 1 shapes with stage 2 SMA20 location filter.

No prior-trend, CCI, entry, stop, trading status or zones.
One-candle signals: only the final bar, with volume exceeding the mean
volume of the preceding 20 bars. Two/three-candle bullish patterns:
completed in the last five bars, without a volume filter.
"""
import math

SINGLE=("HAMMER","REGULAR_DOJI","DRAGONFLY_DOJI")
COMPLEX=("BULLISH_ENGULFING","BULLISH_HARAMI","PIERCING_LINE",
         "TWEEZER_BOTTOM","MORNING_STAR","THREE_INSIDE_UP","THREE_OUTSIDE_UP")


def _bar(d,i):
    x=d.iloc[i]
    o,h,l,c=map(float,(x.open,x.high,x.low,x.close))
    span=max(h-l,1e-10)
    body=abs(c-o)
    return dict(o=o,h=h,l=l,c=c,r=span,body=body,
                green=c>o,red=c<o,
                upper=h-max(o,c),lower=min(o,c)-l)


def _single(d,i):
    b=_bar(d,i)
    if b["body"]/b["r"]<=.1:
        if b["lower"]/b["r"]>=.6 and b["upper"]/b["r"]<=.1:
            return "DRAGONFLY_DOJI"
        return "REGULAR_DOJI"
    if (b["lower"]>=2*max(b["body"],b["r"]*.03)
        and b["upper"]<=b["r"]*.2
        and min(b["o"],b["c"])>=b["l"]+b["r"]*.55):
        return "HAMMER"
    return None


def _complex_at(d,i):
    """All completed geometrical bullish 2/3-bar patterns at index i."""
    b=_bar(d,i)
    matches=[]
    if i>=2:
        z,a=_bar(d,i-2),_bar(d,i-1)
        if (z["red"] and z["body"]/z["r"]>=.45
            and a["body"]<z["body"]*.55
            and b["green"] and b["c"]>(z["o"]+z["c"])/2):
            matches.append(("MORNING_STAR",i-2))
        if (z["red"] and a["green"]
            and z["c"]<=a["o"]<a["c"]<=z["o"]
            and b["green"] and b["c"]>z["o"]):
            matches.append(("THREE_INSIDE_UP",i-2))
        if (z["red"] and a["green"] and a["o"]<=z["c"]
            and a["c"]>=z["o"] and b["green"] and b["c"]>a["c"]):
            matches.append(("THREE_OUTSIDE_UP",i-2))
    if i>=1:
        a=_bar(d,i-1)
        if (a["red"] and b["green"] and b["o"]<=a["c"]
            and b["c"]>=a["o"] and b["body"]>=a["body"]):
            matches.append(("BULLISH_ENGULFING",i-1))
        if (a["red"] and b["green"] and a["c"]<=b["o"]<b["c"]<=a["o"]
            and b["body"]<a["body"]*.8):
            matches.append(("BULLISH_HARAMI",i-1))
        if (a["red"] and b["green"] and b["o"]<=a["c"]
            and (a["o"]+a["c"])/2<=b["c"]<a["o"]):
            matches.append(("PIERCING_LINE",i-1))
        if (a["red"] and b["green"]
            and abs(a["l"]-b["l"])<=max(b["r"]*.15,b["l"]*.003)
            and b["c"]>a["c"]):
            matches.append(("TWEEZER_BOTTOM",i-1))
    return matches


def _valid_sma20_location(d,i):
    """Filter on the COMPLETION candle only, using that day's SMA20.

    A: close < SMA20.
    B: SMA20 <= low <= 1.02 * SMA20.
    This deliberately excludes a low below SMA20 when close is above SMA20,
    as agreed for this layer.
    """
    x=d.iloc[i]
    try:
        sma=float(x.sma20)
        low=float(x.low)
        close=float(x.close)
    except (AttributeError,TypeError,ValueError):
        return False
    if not all(math.isfinite(v) for v in (sma,low,close)) or sma<=0:
        return False
    return close<sma or sma<=low<=sma*1.02


def annotations(d):
    """Return nonoverlapping pattern spans in *visible* bar coordinates.

    The last 5 bars specify pattern completion, not necessarily its start.
    Larger patterns win overlap ties. No setup/entry verdict is implied.
    """
    if len(d)<25:
        return []
    view=d.tail(95).reset_index(drop=True)
    last=len(view)-1
    choices=[]
    for i in range(max(0,last-4),last+1):
        if not _valid_sma20_location(view,i):
            continue
        for name,start in _complex_at(view,i):
            choices.append({"pattern":name,"start":start,"end":i,
                            "kind":"COMPLEX"})
    v=float(view.volume.iloc[-1])
    previous20=float(view.volume.iloc[-21:-1].mean())
    if (_valid_sma20_location(view,last) and math.isfinite(v)
        and math.isfinite(previous20) and v>previous20):
        name=_single(view,last)
        if name:
            choices.append({"pattern":name,"start":last,"end":last,
                            "kind":"SINGLE","volume_ma20":previous20})
    # Give precedence to three-bar, then two-bar, then single-bar.
    # Use most recent end for equal length and stable names for exact ties.
    choices.sort(key=lambda p:(-(p["end"]-p["start"]+1),-p["end"],p["pattern"]))
    taken=set()
    selected=[]
    for p in choices:
        bars=set(range(p["start"],p["end"]+1))
        if taken.isdisjoint(bars):
            selected.append(p)
            taken.update(bars)
    return sorted(selected,key=lambda p:(p["start"],p["end"]))
