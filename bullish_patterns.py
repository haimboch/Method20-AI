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
        if i-2>=window:
            z=bar(i-2)
            if z[3]<z[0] and z[4]/z[5]>=.45 and a[4]<z[4]*.55 and b[3]>b[0] and b[3]>(z[0]+z[3])/2:
                name="MORNING_STAR"
            elif z[3]>z[0] and a[3]>a[0] and b[3]>b[0] and z[3]<a[3]<b[3] and z[0]<a[0]<z[3] and a[0]<b[0]<a[3] and min(z[4]/z[5],a[4]/a[5],b[4]/b[5])>=.4:
                name="THREE_WHITE_SOLDIERS"
            elif z[3]<z[0] and a[3]>a[0] and z[3]<=a[0]<a[3]<=z[0] and b[3]>z[0]:
                name="THREE_INSIDE_UP"
            elif z[3]<z[0] and a[3]>a[0] and a[0]<=z[3] and a[3]>=z[0] and b[3]>a[3] and b[3]>b[0]:
                name="THREE_OUTSIDE_UP"
            if name:
                width=3
        if not name:
            if a[3]<a[0] and b[3]>b[0] and b[0]<=a[3] and b[3]>=a[0]:
                name="BULLISH_ENGULFING"
            elif a[3]<a[0] and b[3]>b[0] and a[3]<=b[0]<b[3]<=a[0] and b[4]<a[4]*.8:
                name="BULLISH_HARAMI"
            elif a[3]<a[0] and b[3]>b[0] and b[0]<=a[3] and (a[0]+a[3])/2<=b[3]<a[0] and a[4]/a[5]>=.4:
                name="PIERCING_LINE"
            elif a[3]<a[0] and b[3]>b[0] and abs(a[2]-b[2])<=max(abs(a[2]),.01)*.003:
                name="TWEEZER_BOTTOM"
