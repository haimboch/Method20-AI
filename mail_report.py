"""Send the latest validated EOD artifact by Gmail SMTP, without rerunning AI."""
import io
import html
import json
import os
import smtplib
import zipfile
from datetime import datetime, timedelta
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal
import requests
from PIL import Image
from report_format import fmt2, format_numbers_in_text
from report_sections import grouped_results, section_key, signal_for_display, signal_explanation

TO="Haimboch@gmail.com"
API="https://api.github.com"
MAX_ATTACHMENT=18*1024*1024

def delivery_decision(event, now=None):
    now=now or datetime.now(ZoneInfo("UTC"))
    if not now.tzinfo:
        raise ValueError("timezone-aware datetime required")
    israel=now.astimezone(ZoneInfo("Asia/Jerusalem"))
    if event=="schedule" and not (6<=israel.hour<=9):
        return False,None,"Outside Israeli 06:00-09:59 delivery window"
    calendar=mcal.get_calendar("NYSE")
    day=now.astimezone(ZoneInfo("America/New_York")).date()
    sessions=calendar.schedule(start_date=day-timedelta(days=7),end_date=day)
    closed=sessions[sessions["market_close"]<=now]
    if closed.empty:
        return False,None,"No closed NYSE session in prior week"
    session=closed.iloc[-1]
    session_date=closed.index[-1].date()
    # Prevent stale reporting on holidays or in case of missed nightly jobs.
    monday_report=(event=="schedule" and israel.weekday()==0 and session_date.weekday()==4)
    max_age=timedelta(hours=72) if monday_report or event!="schedule" else timedelta(hours=18)
    if now-session["market_close"].to_pydatetime()>max_age:
        return False,session_date,"No recently completed NYSE session within allowed window"
    return True,session_date,"Eligible last closed NYSE session"

def github_get(session,path,params=None):
    r=session.get(API+path,params=params,timeout=40)
    r.raise_for_status()
    return r.json()

def already_sent(session,repo,session_date):
    """Only an explicit artifact uploaded after successful SMTP send counts."""
    marker="method20-sent-"+session_date.isoformat()
    artifacts=github_get(
        session,"/repos/"+repo+"/actions/artifacts",
        {"name":marker,"per_page":100}
    ).get("artifacts",[])
    exists=any(x.get("name")==marker and not x.get("expired") for x in artifacts)
    print("EMAIL_DELIVERY_MARKER session="+session_date.isoformat()
          +" exists="+str(exists),flush=True)
    return exists

def find_artifact(session,repo,session_date,now):
    runs=github_get(session,"/repos/"+repo+"/actions/workflows/report.yml/runs",
                    {"per_page":50,"status":"success"}).get("workflow_runs",[])
    for run in runs:
        created=datetime.fromisoformat(run["created_at"].replace("Z","+00:00"))
        age=now-created
        if not timedelta(0)<=age<=timedelta(hours=72):
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
                if "metadata.json" not in names:
                    print("SKIP_LEGACY_ARTIFACT run="+str(run["id"])+" missing metadata.json; regenerate EOD report",flush=True)
                    continue
                meta=json.loads(z.read("metadata.json"))
                if (meta.get("session_date")!=session_date.isoformat()
                    or not meta.get("complete")):
                    continue
                if "report.html" not in names or "results.json" not in names:
                    continue
                results=json.loads(z.read("results.json"))
                if not results or any("error" in item for item in results):
                    continue
                return raw,results,run["html_url"]
    raise LookupError("No complete and verified EOD artifact for NYSE session "+session_date.isoformat())

def regenerate_missing_report(session_date):
    """Recovery only: fetch the exact closed trading session and rebuild the report.

    Regenerates source-based technical data only when no complete artifact exists. Fail closed on
    missing/old data or partial ticker coverage.
    """
    from pathlib import Path
    import engine
    print("EOD_RECOVERY_START session="+session_date.isoformat(),flush=True)
    previous=os.environ.get("EXPECTED_SESSION_DATE")
    os.environ["EXPECTED_SESSION_DATE"]=session_date.isoformat()
    try:
        engine.main()
    finally:
        if previous is None:
            os.environ.pop("EXPECTED_SESSION_DATE",None)
        else:
            os.environ["EXPECTED_SESSION_DATE"]=previous
    root=Path(engine.OUT)
    meta=json.loads((root/"metadata.json").read_text(encoding="utf-8"))
    results=json.loads((root/"results.json").read_text(encoding="utf-8"))
    if (meta.get("session_date")!=session_date.isoformat()
        or not meta.get("complete") or not results
        or len(results)!=meta.get("expected_ticker_count")
        or any("error" in r for r in results)):
        raise RuntimeError("Recovered report failed complete-date-and-data validation")
    contents=io.BytesIO()
    with zipfile.ZipFile(contents,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for p in root.rglob("*"):
            if p.is_file():
                z.write(p,p.relative_to(root).as_posix())
    raw=contents.getvalue()
    if len(raw)>MAX_ATTACHMENT:
        raise ValueError("Recovered report exceeds archive size limit")
    repo=os.getenv("GITHUB_REPOSITORY","haimboch/Method20-AI")
    run_id=os.getenv("GITHUB_RUN_ID","")
    run_url=("https://github.com/"+repo+"/actions/runs/"+run_id
             if run_id else "https://github.com/"+repo+"/actions")
    print("EOD_RECOVERY_COMPLETE session="+session_date.isoformat()+
          " tickers="+str(len(results)),flush=True)
    return raw,results,run_url

def compact_chart(image_bytes):
    """Reduce chart size for inline Gmail display, preserving source archive."""
    with Image.open(io.BytesIO(image_bytes)) as im:
        im=im.convert("RGB")
        im.thumbnail((1350,1100))
        out=io.BytesIO()
        im.save(out,format="JPEG",quality=72,optimize=True)
        return out.getvalue()

def make_message(raw,results,session_date,run_url):
    """Send chart-first report and current portfolio/stop alerts inline."""
    ordered=[item for _,_,items in grouped_results(results) for item in items]
    msg=EmailMessage()
    msg["From"]=TO;msg["To"]=TO
    msg["Subject"]="METHOD 20 | דוח מסחר "+session_date.isoformat()
    msg.set_content("METHOD 20: "+session_date.isoformat()
                    +"\nגרפים יומיים, סטאפים, פוזיציות והתראות סטופ.")
    parts=['<!doctype html><html lang="he" dir="rtl"><meta charset="utf-8">',
           '<body style="margin:0;padding:16px;font-family:Arial,sans-serif;background:#f2f5f9">',
           '<div style="max-width:1200px;margin:auto"><h1>METHOD 20</h1>']
    images=[]
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        portfolio=json.loads(z.read("portfolio.json")) if "portfolio.json" in z.namelist() else {"rows":[],"alerts":[]}
        if portfolio["alerts"]:
            parts.append('<section style="background:#fff0e9;padding:12px;border-radius:10px">'
                         +'<h2>התראות סטופ | בדוק ביצוע בפועל</h2>')
            for a in portfolio["alerts"]:
                parts.append('<p><b>'+html.escape(a["symbol"])+'</b> | סטופ $'
                            +fmt2(a["stop"])+' | שפל $'+fmt2(a["low"])
                            +' | '+html.escape(str(a["date"]))+'</p>')
            parts.append('</section>')
        if portfolio["rows"]:
            parts.append('<h2>פוזיציות פתוחות</h2><table border="1" cellspacing="0" cellpadding="7" '
                         +'style="border-collapse:collapse;background:white;max-width:100%">'
                         +'<tr><th>מניה</th><th>כמות</th><th>כניסה</th><th>סטופ</th>'
                         +'<th>סגירה</th><th>ממומש</th><th>לא ממומש</th><th>סיכון לסטופ</th></tr>')
            for p in portfolio["rows"]:
                def money(v):
                    return "$"+fmt2(v) if v is not None else "—"
                parts.append('<tr><td>'+html.escape(p["symbol"])+'</td><td>'
                             +fmt2(p["quantity"])+'</td><td>'+money(p["entry"])
                             +'</td><td>'+money(p["stop"])+'</td><td>'
                             +money(p["last_close"])+'</td><td>'+money(p["realized"])
                             +'</td><td>'+money(p["unrealized"])+'</td><td>'
                             +money(p["risk_to_stop"])+'</td></tr>')
            parts.append('</table>')
        for index,item in enumerate(ordered):
            sym=html.escape(item["symbol"])
            parts.append('<section style="background:white;padding:14px;margin:16px 0;border-radius:12px">'
                         +'<h2>'+sym+'</h2>')
            if "error" in item:
                parts.append('<p>נתונים לא זמינים</p></section>')
                continue
            signal=item.get("analysis",{}).get("active")
            if signal:
                parts.append('<p>'+html.escape(signal["status"])+' | '
                             +html.escape(signal["setup"])+' | '
                             +html.escape(signal["pattern"])+' | טריגר $'
                             +fmt2(signal["high"])+' | סטופ טכני $'
                             +fmt2(signal["low"])+'</p>')
            if item.get("risk_reward") is not None:
                parts.append('<p>יחס סיכוי־סיכון משוער: 1:'
                             +fmt2(item["risk_reward"])+' (מידע בלבד)</p>')
            chart_name="charts/"+item["symbol"]+".png"
            if chart_name not in z.namelist():
                raise ValueError("Missing chart image: "+chart_name)
            cid="method20-chart-"+str(index)+"@local"
            images.append((cid,compact_chart(z.read(chart_name))))
            parts.append('<img alt="1D candles SMA20 VOL CCI14" src="cid:'+cid+'" '
                         +'style="display:block;width:100%;height:auto"/></section>')
    parts.append('<p style="font-size:12px">מידע למחקר בלבד. '
                 +'נגיעה בסטופ אינה מוכיחה שבוצעה מכירה.</p></div></body></html>')
    msg.add_alternative("".join(parts),subtype="html")
    htmlpart=msg.get_payload()[-1]
    for cid,content in images:
        htmlpart.add_related(content,maintype="image",subtype="jpeg",
                             cid="<"+cid+">",disposition="inline")
    if len(msg.as_bytes())>18*1024*1024:
        raise ValueError("Inline email exceeds 18 MB safety limit")
    return msg

def main():
    now=datetime.now(ZoneInfo("UTC"))
    event=os.getenv("GITHUB_EVENT_NAME","workflow_dispatch")
    eligible,session_date,reason=delivery_decision(event,now)
    print("Delivery gate:",reason,"session:",session_date,flush=True)
    if not eligible:
        print("DELIVERY_SKIPPED event="+event+" reason="+reason,flush=True)
        if event=="workflow_dispatch":
            raise RuntimeError("Manual email delivery blocked: "+reason)
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
    if already_sent(session,repo,session_date):
        print("EMAIL_ALREADY_SENT session="+session_date.isoformat(),flush=True)
        return
    try:
        raw,results,url=find_artifact(session,repo,session_date,now)
        print("EOD_EXISTING_ARTIFACT_FOUND session="+session_date.isoformat(),flush=True)
    except LookupError:
        print("EOD_ARTIFACT_MISSING initiating verified recovery",flush=True)
        raw,results,url=regenerate_missing_report(session_date)
    msg=make_message(raw,results,session_date,url)
    with smtplib.SMTP_SSL("smtp.gmail.com",465,timeout=45) as smtp:
        smtp.login(TO,password)
        smtp.send_message(msg)
    from pathlib import Path
    Path("delivery_marker.txt").write_text(
        "SMTP send accepted for NYSE session "+session_date.isoformat()+"\n",
        encoding="utf-8")
    dest=os.getenv("GITHUB_OUTPUT")
    if dest:
        with open(dest,"a",encoding="utf-8") as output:
            output.write("sent=true\n")
            output.write("session_date="+session_date.isoformat()+"\n")
    print("METHOD20_EMAIL_SENT session="+session_date.isoformat()
          +" recipient="+TO,flush=True)

if __name__=="__main__":
    main()
