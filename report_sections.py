"""Shared METHOD 20 section ordering and signal explanations."""

SECTIONS=(
    ("READY","סטאפים מוכנים לפריצה"),
    ("TRIGGERED","סטאפים שהטריגר שלהם נפרץ"),
    ("CANDIDATE","תבניות מועמדות ללא אישור מלא"),
    ("OTHER","מניות ללא סטאפ כניסה תקף"),
)

def section_key(item):
    analysis=item.get("analysis") or {}
    if item.get("display_status")=="HISTORICAL_TRIGGER":
        return "OTHER"
    status=analysis.get("status")
    if status=="READY" and analysis.get("active"):
        return "READY"
    active=analysis.get("active") or {}
    if status=="CANDIDATE" and active.get("status")=="CANDIDATE":
        return "CANDIDATE"
    if status=="TRIGGERED" and active.get("status")=="TRIGGERED":
        return "TRIGGERED"
    last=analysis.get("last_event") or {}
    if status=="TRIGGERED" and last.get("status")=="TRIGGERED":
        return "TRIGGERED"
    return "OTHER"

def grouped_results(results):
    return [(key,title,[item for item in results if section_key(item)==key])
            for key,title in SECTIONS]

SETUP_DESCRIPTION={
    "A: MEAN_REVERSION":"היפוך אפשרי אחרי ירידה מתחת ל-SMA20, עם CCI שהגיע למכירות יתר, שינוי כיוון ב-CCI ונפח תומך.",
    "B: SMA20_BOUNCE":"ניסיון לקפיצה מאזור התמיכה של SMA20 עם נר/תבנית היפוך, CCI שמתחיל לעלות ונפח תומך.",
}
PATTERN_DESCRIPTION={
    "DOJI":"דוג׳י (חוסר החלטיות)",
    "HAMMER":"פטיש (דחיית מחירים נמוכים)",
    "BULLISH_ENGULFING":"בליעה שורית",
    "BULLISH_HARAMI":"הראמי שורי",
    "MORNING_STAR":"כוכב בוקר",
    "THREE_WHITE_SOLDIERS":"שלושה חיילים לבנים",
    "PIERCING_LINE":"נר חודר שורי",
    "TWEEZER_BOTTOM":"תחתית פינצטה",
    "THREE_INSIDE_UP":"שלושה בפנים כלפי מעלה",
    "THREE_OUTSIDE_UP":"שלושה בחוץ כלפי מעלה",
    "BULLISH_REJECTION":"דחייה שורית",
}
def signal_for_display(item):
    a=item.get("analysis") or {}
    key=section_key(item)
    return (a.get("active") if key in ("READY","CANDIDATE")
            else (a.get("active") or a.get("last_event")) if key=="TRIGGERED" else None)

def signal_explanation(signal):
    if not signal: return None
    setup=signal.get("setup","")
    label=PATTERN_DESCRIPTION.get(signal.get("pattern"),signal.get("pattern","נר היפוך"))
    basis=SETUP_DESCRIPTION.get(setup,"סטאפ שעומד בתנאי METHOD 20.")
    return basis+" תצורת האיתות: "+label+"."
