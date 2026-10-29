"""Multi-candle bullish chart patterns, independent of trade signals."""
PATTERNS={"BULLISH_ENGULFING":"Engulfing","BULLISH_HARAMI":"Harami","MORNING_STAR":"Morning Star","THREE_WHITE_SOLDIERS":"Three White Soldiers","PIERCING_LINE":"Piercing Line","TWEEZER_BOTTOM":"Tweezer Bottom","THREE_INSIDE_UP":"Three Inside Up","THREE_OUTSIDE_UP":"Three Outside Up"}

def detect(d,last_n=10):
    n=len(d)
    window=max(0,n-last_n)
    result=[]
    def bar(i):
        x=d.iloc[i]
        o,h,l,c=(float(x[k]) for k in ("open","high","low","close"))
        return o,h,l,c,abs(c-o),max(h-l,1e-8)
    for i in range(window+1,n):
        a=bar(i-1)
        b=bar(i)
        name=None
        width=2
