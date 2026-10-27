"""Determine a closed NYSE session for morning mail, exporting GitHub outputs."""
import os
from mail_report import delivery_decision

if __name__=="__main__":
    event=os.getenv("GITHUB_EVENT_NAME","workflow_dispatch")
    ok,date,reason=delivery_decision(event)
    print("MORNING_GATE",event,ok,date,reason,flush=True)
    with open(os.environ["GITHUB_OUTPUT"],"a",encoding="utf-8") as out:
        out.write("should_run="+str(ok).lower()+"\n")
        out.write("session_date="+(date.isoformat() if date else "none")+"\n")
    if not ok and event=="workflow_dispatch":
        raise RuntimeError("Manual morning delivery skipped: "+reason)
