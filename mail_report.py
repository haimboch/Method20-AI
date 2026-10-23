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
    max_age=timedelta(hours=18) if event=="schedule" else timedelta(hours=72)
    if now-session["market_close"].to_pydatetime()>max_age:
        return False,session_date,"No recently completed NYSE session within allowed window"
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
                # Require visual reviews for each ticker before emailing complete report.
                if any(item.get("ai_review",{}).get("status")!="COMPLETE" for item in results):
                    raise ValueError("A completed nightly report has incomplete AI reviews")
                return raw,results,run["html_url"]
    raise LookupError("No complete and verified EOD artifact for NYSE session "+session_date.isoformat())

def compact_chart(image_bytes):
    """Reduce chart size for inline Gmail display, preserving source archive."""
    with Image.open(io.BytesIO(image_bytes)) as im:
        im=im.convert("RGB")
        im.thumbnail((1050,850))
        out=io.BytesIO()
        im.save(out,format="JPEG",quality=72,optimize=True)
        return out.getvalue()

def make_message(raw,results,session_date,run_url):
    """Render the report *inside* the email. No ZIP or extraction required."""
    ready=[r["symbol"] for r in results if r["analysis"]["status"]=="READY"]
    triggered=[r["symbol"] for r in results if r["analysis"]["status"]=="TRIGGERED"]
    msg=EmailMessage()
    msg["From"]=TO
    msg["To"]=TO
    msg["Subject"]="METHOD 20 AI | דוח מסחר "+session_date.isoformat()
    msg.set_content(
        "METHOD 20 AI: "+session_date.isoformat()+"\n"
        +"מניות שנותחו: "+str(len(results))+"\n"
        +"READY: "+(", ".join(ready) if ready else "אין")+"\n"
        +"TRIGGERED: "+(", ".join(triggered) if triggered else "אין")+"\n"
        +"הדוח המלא, כולל הגרפים והניתוח, מופיע בגרסת HTML של הודעה זו.\n"
        +"מקור: "+run_url+"\n"
    )
    parts=[
        '<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8"></head>',
        '<body style="margin:0;padding:18px;font-family:Arial,sans-serif;background:#f2f5f9;color:#162638">',
        '<div style="max-width:840px;margin:auto">',
        '<h1 style="margin:0 0 8px">METHOD 20 AI</h1>',
        '<p>דוח מסחר '+html.escape(session_date.isoformat())+' | '+str(len(results))+' מניות</p>',
        '<div style="padding:14px;background:#e8eef6;border-radius:10px">',
        '<b>READY:</b> '+html.escape(", ".join(ready) if ready else "אין"),
        ' | <b>TRIGGERED:</b> '+html.escape(", ".join(triggered) if triggered else "אין"),
        '</div>',
        '<p style="font-size:12px">הסטאפים הם אותות מחקריים בלבד, לא הוראות מסחר. התרחישים מותנים ולא תחזיות ודאיות.</p>'
    ]
    images=[]
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for index,item in enumerate(results):
            sym=html.escape(item["symbol"])
            a=item["analysis"]
            ai=item.get("ai_review",{})
            levels=item.get("levels",{})
            outlook=item.get("outlook",{})
            def prices(name):
                entries=levels.get(name,[])
                return ", ".join("$"+format(float(v["price"]),".2f") for v in entries) if entries else "לא זוהתה"
            def safe(value):
                return html.escape(str(value if value is not None else "לא זמין"))
            parts.extend([
                '<section style="background:white;margin:18px 0;padding:16px;border-radius:12px;border:1px solid #e1e6ed">',
                '<h2 style="margin:0 0 8px">'+sym+' | '+safe(a.get("status"))+'</h2>',
                '<p><b>סגירה:</b> $'+safe(a.get("close"))+' | <b>SMA20:</b> $'+safe(a.get("sma20"))
                +' | <b>CCI14:</b> '+safe(a.get("cci14"))+' | <b>נפח:</b> '+safe(a.get("volume_ratio"))+'x</p>',
                '<p><b>מגמת 5 ימים:</b> '+safe(a.get("change_5d_pct"))+'% | <b>21 ימים:</b> '+safe(a.get("change_21d_pct"))+'%</p>',
                '<p><b>תמיכות:</b> '+safe(prices("support"))+' | <b>התנגדויות:</b> '+safe(prices("resistance"))+'</p>',
                '<p><b>תחזית מותנית ליום הבא:</b> '+safe(outlook.get("bias"))+'</p>',
                '<p>'+safe(outlook.get("reason"))+'</p>',
                '<p><b>תרחיש שורי:</b> '+safe(outlook.get("bull_case"))+'</p>',
                '<p><b>תרחיש דובי:</b> '+safe(outlook.get("bear_case"))+'</p>',
            ])
            active=a.get("active")
            if active:
                parts.append('<p><b>סטאפ פעיל:</b> '+safe(active.get("setup"))
                             +'; HIGH: $'+safe(active.get("high"))
                             +'; LOW: $'+safe(active.get("low"))+'</p>')
            chart_name="charts/"+item["symbol"]+".png"
            if chart_name not in z.namelist():
                raise ValueError("Missing chart image: "+chart_name)
            cid="method20-chart-"+str(index)+"@local"
            image_data=compact_chart(z.read(chart_name))
            images.append((cid,image_data))
            parts.append('<img alt="Daily '+sym+' chart" src="cid:'+cid+'" '
                         'style="display:block;width:100%;height:auto;margin:12px 0"/>')
            parts.extend([
                '<h3 style="margin:12px 0 6px">ניתוח AI חזותי</h3>',
                '<p style="line-height:1.6;white-space:pre-line">'+safe(ai.get("text"))+'</p>',
                '</section>'
            ])
    parts.extend(['<p style="font-size:12px">מקור הדוח: <a href="'
                  +html.escape(run_url,quote=True)+'">GitHub Actions</a>. '
                  'מידע למחקר בלבד.</p>','</div></body></html>'])
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
    raw,results,url=find_artifact(session,repo,session_date,now)
    msg=make_message(raw,results,session_date,url)
    with smtplib.SMTP_SSL("smtp.gmail.com",465,timeout=45) as smtp:
        smtp.login(TO,password)
        smtp.send_message(msg)
    print("METHOD20_EMAIL_SENT session="+session_date.isoformat()
          +" recipient="+TO,flush=True)

if __name__=="__main__":
    main()
