"""Schedule guard for METHOD 20.

GitHub cron uses UTC. Run at 20:40 and 21:40 UTC, then only proceed
in the Israel 23:30–00:29 window after an actual NYSE session.
Workflow dispatch always allowed. Do NOT confuse this with guaranteed delivery.
"""
from datetime import datetime, time
from zoneinfo import ZoneInfo
import os
import pandas_market_calendars as mcal

def decide(event, now_utc=None):
    now_utc=now_utc or datetime.now(ZoneInfo("UTC"))
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    israel=now_utc.astimezone(ZoneInfo("Asia/Jerusalem"))
    ny=now_utc.astimezone(ZoneInfo("America/New_York"))
    day=ny.date()
    if event != "schedule":
        return {"run":True,"reason":"manual run","session_date":day.isoformat(),
                "israel_time":israel.isoformat()}
    # The 00:xx grace window catches a delayed GitHub Actions schedule.
    in_window=(israel.hour==23 and israel.minute>=30) or (israel.hour==0 and israel.minute<=29)
    if not in_window:
        return {"run":False,"reason":"outside Israel EOD window",
                "session_date":day.isoformat(),"israel_time":israel.isoformat()}
    calendar=mcal.get_calendar("NYSE")
    sessions=calendar.schedule(start_date=day,end_date=day)
    if sessions.empty:
        return {"run":False,"reason":"NYSE closed (weekend/holiday)",
                "session_date":day.isoformat(),"israel_time":israel.isoformat()}
    close_time=sessions.iloc[0]["market_close"].to_pydatetime()
    if now_utc<close_time:
        return {"run":False,"reason":"NYSE session not closed yet",
                "session_date":day.isoformat(),"israel_time":israel.isoformat()}
    return {"run":True,"reason":"eligible completed NYSE session",
            "session_date":day.isoformat(),"israel_time":israel.isoformat()}

def main():
    event=os.getenv("GITHUB_EVENT_NAME","workflow_dispatch")
    decision=decide(event)
    print("Scheduler:",decision)
    dest=os.getenv("GITHUB_OUTPUT")
    if dest:
        with open(dest,"a",encoding="utf8") as f:
            f.write("should_run="+str(decision["run"]).lower()+"\n")
            f.write("session_date="+decision["session_date"]+"\n")
    if not decision["run"]:
        print("SKIPPED:",decision["reason"])

if __name__=="__main__":
    main()
