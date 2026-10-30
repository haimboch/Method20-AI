"""Manual-only METHOD20 trade ledger, driven by GitHub Actions workflow_dispatch.

No broker connectivity or order placement. The append-only event log is authoritative.
"""
import json,os,sys,uuid
from datetime import datetime,timezone
from pathlib import Path

DATA=Path(__file__).resolve().parent/"data"/"trade_events.json"
ACTIONS={"BUY","SELL_PARTIAL","UPDATE_STOP","CLOSE","SKIP_TRADE"}

def load(path=DATA):
    if not Path(path).exists():return []
    events=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(events,list):raise ValueError("Ledger must be an array")
    return events

def replay(events):
    positions={};history=[];skipped=set();closed_signal_dates={}
    for event in events:
        symbol=event["symbol"].upper();action=event["action"]
        p=positions.get(symbol)
        if action=="BUY":
            if p:raise ValueError(symbol+" already has an open position; additions prohibited")
            qty=float(event["quantity"]);price=float(event["price"]);stop=float(event["stop"])
            if qty<=0 or price<=0 or stop<=0:raise ValueError("Invalid buy fields")
            positions[symbol]={"symbol":symbol,"quantity":qty,"initial_quantity":qty,
                                "entry":price,"initial_stop":stop,"stop":stop,
                                "realized":0.0,"status":"OPEN","signal_date":event.get("signal_date"),
                                "stop_effective_date":event["date"],
                                "fee_total":float(event.get("fee") or 0)}
        elif action=="SKIP_TRADE":
            if p:raise ValueError("Cannot skip an open position")
            if event.get("signal_date"):
                skipped.add((symbol,event["signal_date"]))
                closed_signal_dates.setdefault(symbol,set()).add(event["signal_date"])
            history.append(event)
        elif action=="UPDATE_STOP":
            if not p:raise ValueError("No open position to update stop")
            new_stop=float(event["stop"])
            if new_stop<p["stop"]:raise ValueError("Long stop may never be lowered")
            p["stop"]=new_stop;p["stop_effective_date"]=event["date"]
        elif action in ("SELL_PARTIAL","CLOSE"):
            if not p:raise ValueError("No open position to sell")
            qty=p["quantity"] if action=="CLOSE" else float(event["quantity"])
            price=float(event["price"])
            if qty<=0 or qty>p["quantity"] or price<=0:raise ValueError("Invalid sale")
            if action=="SELL_PARTIAL" and qty==p["quantity"]:
                raise ValueError("Use CLOSE to sell the entire remaining position")
            p["realized"]+=qty*(price-p["entry"])
            p["quantity"]-=qty
            p["fee_total"]+=float(event.get("fee") or 0)
            if p["quantity"]==0:
                p["status"]="CLOSED";p["closed_date"]=event["date"]
                if p.get("signal_date"):
                    closed_signal_dates.setdefault(symbol,set()).add(p["signal_date"])
                history.append(dict(p));del positions[symbol]
            else:p["status"]="PARTIAL"
    return positions,history,closed_signal_dates

def add_event(path,event):
    events=load(path)
    if event.get("action") not in ACTIONS:raise ValueError("Unknown action")
    if not event.get("symbol"):raise ValueError("Symbol required")
    event=dict(event);event["symbol"]=event["symbol"].strip().upper()
    event["date"]=event.get("date") or datetime.now(timezone.utc).date().isoformat()
    datetime.strptime(event["date"],"%Y-%m-%d")
    event["id"]=event.get("id") or str(uuid.uuid4())
    if any(e["id"]==event["id"] for e in events):raise ValueError("Duplicate event")
    # Validate full event history before persisting.
    replay(events+[event])
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(events+[event],ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return event

def report_rows(events,market_data):
    positions,_,_=replay(events)
    rows=[];alerts=[]
    for symbol,p in sorted(positions.items()):
        market=market_data.get(symbol,{})
        close=market.get("close")
        low=market.get("low")
        day=market.get("date")
        remaining=p["quantity"]
        unrealized=(close-p["entry"])*remaining if close is not None else None
        to_stop=max(0,(close-p["stop"])*remaining) if close is not None else None
        row={**p,"last_close":close,"unrealized":unrealized,"risk_to_stop":to_stop}
        rows.append(row)
        # Only check the known session if stop was already in force.
        if low is not None and day is not None and str(day)>=p["stop_effective_date"] and low<=p["stop"]:
            alerts.append({"symbol":symbol,"stop":p["stop"],"low":low,
                           "date":str(day),"quantity":remaining})
    return rows,alerts

def main():
    action=os.environ["TRADE_ACTION"].strip().upper()
    event={"action":action,"symbol":os.environ["TRADE_SYMBOL"],
           "date":os.getenv("TRADE_DATE","").strip() or None,
           "signal_date":os.getenv("TRADE_SIGNAL_DATE","").strip() or None}
    for field,env in [("quantity","TRADE_QUANTITY"),("price","TRADE_PRICE"),
                      ("stop","TRADE_STOP"),("fee","TRADE_FEE")]:
        value=os.getenv(env,"").strip()
        if value:event[field]=float(value)
    if action=="BUY":
        for field in ("quantity","price","stop"):
            if field not in event:raise ValueError("BUY requires "+field)
    elif action in ("SELL_PARTIAL","CLOSE"):
        if "price" not in event or (action=="SELL_PARTIAL" and "quantity" not in event):
            raise ValueError(action+" requires price and partial sale quantity")
    elif action=="UPDATE_STOP" and "stop" not in event:
        raise ValueError("UPDATE_STOP requires stop")
    add_event(DATA,event)
    print("TRADE_LEDGER_UPDATED action="+action+" symbol="+event["symbol"].upper())

if __name__=="__main__":main()
