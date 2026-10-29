"""Shared METHOD 20 section ordering and signal explanations."""

SECTIONS=(
    ("READY","סטאפים מוכנים לפריצה"),
    ("TRIGGERED","סטאפים שהטריגר שלהם נפרץ"),
    ("OTHER","מניות ללא סטאפ כניסה תקף"),
)

def section_key(item):
    analysis=item.get("analysis") or {}
    status=analysis.get("status")
    if status=="READY" and analysis.get("active"):
        return "READY"
    last=analysis.get("last_event") or {}
    if status=="TRIGGERED" and last.get("status")=="TRIGGERED":
        return "TRIGGERED"
    return "OTHER"

def grouped_results(results):
    return [(key,title,[item for item in results if section_key(item)==key])
            for key,title in SECTIONS]
