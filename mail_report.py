"""Send the latest validated EOD artifact by Gmail SMTP, without rerunning AI."""
import io
import json
import os
import smtplib
import zipfile
from datetime import datetime, timedelta
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal
import requests

TO="Haimboch@gmail.com"
API="https://api.github.com"
MAX_ATTACHMENT=18*1024*1024

def delivery_decision(event, now=None):
    now=now or datetime.now(ZoneInfo("UTC"))
    if not now.tzinfo:
        raise ValueError("timezone-aware datetime required")
    israel=now.astimezone(ZoneInfo("Asia/Jerusalem"))
    if event=="schedule" and not (israel.hour==6 and israel.minute<=59):
        return False,None,"Outside Israeli 06:00-06:59 delivery window"
    calendar=mcal.get_calendar("NYSE")
    day=now.astimezone(ZoneInfo("America/New_York")).date()
    sessions=calendar.schedule(start_date=day-timedelta(days=7),end_date=day)
    closed=sessions[sessions["market_close"]<=now]
    if closed.empty:
        return False,None,"No closed NYSE session in prior week"
    session=closed.iloc[-1]
    session_date=closed.index[-1].date()
    # Prevent stale reporting on holidays or in case of missed nightly jobs.
    if now-session["market_close"].to_pydatetime()>timedelta(hours=18):
        return False,session_date,"No recently completed NYSE session"
    return True,session_date,"Eligible last closed NYSE session"

def github_get(session,path,params=None):
    r=session.get(API+path,params=params,timeout=40)
    r.raise_for_status()
    return r.json()

def find_artifact(session,repo,session_date,now):
    runs=github_get(session,"/repos/"+repo+"/actions/workflows/report.yml/runs",
                    {"per_page":50,"status":"success"}).get("workflow_runs",[])
    for run in runs:
        created=datetime.fromisoformat(run["created_at"].replace("Z","+00:00"))
        age=now-created
        if not timedelta(0)<=age<=timedelta(hours=48):
            continue
        artifacts=github_get(session,"/repos/"+repo+"/actions/runs/"+str(run["id"])+"/artifacts",
                            {"per_page":100}).get("artifacts",[])
        for artifact in artifacts:
            if artifact.get("name")!="method20-html-report" or artifact.get("expired"):
                continue
            response=session.get(artifact["archive_download_url"],timeout=90)
            response.raise_for_status()
            raw=response.content
            if len(raw)>MAX_ATTACHMENT:
                raise ValueError("Report ZIP exceeds Gmail safe 18 MB attachment limit")
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                names=z.namelist()
                meta=json.loads(z.read("metadata.json"))
                if (meta.get("session_date")!=session_date.isoformat()
                    or not meta.get("complete")):
                    continue
                if "report.html" not in names or "results.json" not in names:
                    continue
                results=json.loads(z.read("results.json"))
                if not results or any("error" in item for item in results):
                    continue
                # Require visual reviews for each ticker before emailing complete report.
                if any(item.get("ai_review",{}).get("status")!="COMPLETE" for item in results):
                    raise ValueError("A completed nightly report has incomplete AI reviews")
                return raw,results,run["html_url"]
    raise LookupError("No complete and verified EOD artifact for NYSE session "+session_date.isoformat())

def make_message(raw,results,session_date,run_url):
    ready=[r["symbol"] for r in results if r["analysis"]["status"]=="READY"]
    triggered=[r["symbol"] for r in results if r["analysis"]["status"]=="TRIGGERED"]
    msg=EmailMessage()
    msg["From"]=TO
    msg["To"]=TO
    msg["Subject"]="METHOD 20 AI | דוח מסחר "+session_date.isoformat()
    body=("דוח METHOD 20 AI ליום המסחר "+session_date.isoformat()+"\n\n"
          +"מניות שנבדקו: "+str(len(results))+"\n"
          +"READY: "+(", ".join(ready) if ready else "אין")+"\n"
          +"TRIGGERED: "+(", ".join(triggered) if triggered else "אין")+"\n\n"
          +"דוח HTML עם הגרפים מצורף כקובץ ZIP. חלץ את כל הקבצים "
          +"ופתח את report.html לצד תיקיית charts.\n\n"
          +"קישור להרצה: "+run_url+"\n\n"
          +"מחקר טכני בלבד, ללא הוראות מסחר.")
    msg.set_content(body)
    msg.add_attachment(raw,maintype="application",subtype="zip",
                       filename="method20-"+session_date.isoformat()+".zip")
    return msg

def main():
    now=datetime.now(ZoneInfo("UTC"))
    event=os.getenv("GITHUB_EVENT_NAME","workflow_dispatch")
    eligible,session_date,reason=delivery_decision(event,now)
    print("Delivery gate:",reason,"session:",session_date,flush=True)
    if not eligible:
        return
    token=os.getenv("GITHUB_TOKEN","").strip()
    password=os.getenv("GMAIL_APP_PASSWORD","").replace(" ","").strip()
    repo=os.getenv("GITHUB_REPOSITORY","haimboch/Method20-AI")
    if not token:
        raise RuntimeError("Missing GITHUB_TOKEN")
    if not password:
        raise RuntimeError("Missing GMAIL_APP_PASSWORD GitHub Actions secret")
    session=requests.Session()
    session.headers.update({"Authorization":"Bearer "+token,
                            "Accept":"application/vnd.github+json",
                            "X-GitHub-Api-Version":"2022-11-28"})
    raw,results,url=find_artifact(session,repo,session_date,now)
    msg=make_message(raw,results,session_date,url)
    with smtplib.SMTP_SSL("smtp.gmail.com",465,timeout=45) as smtp:
        smtp.login(TO,password)
        smtp.send_message(msg)
    print("METHOD20_EMAIL_SENT session="+session_date.isoformat()
          +" recipient="+TO,flush=True)

if __name__=="__main__":
    main()
