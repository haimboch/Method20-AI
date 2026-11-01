"""Fast single-ticker Stage 1 test without GitHub Actions or email.

Examples:
    python quick_test.py --ticker BE --csv data/BE.csv
    MASSIVE_API_KEY=... python quick_test.py --ticker BE --fetch
    python quick_test.py --ticker BE --csv data/BE.csv --check-tests
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
from engine import annotations, chart, fetch, indicators, render
import engine


def load_csv(path):
    data=pd.read_csv(path)
    data.columns=[str(x).strip().lower() for x in data.columns]
    required=("date","open","high","low","close","volume")
    missing=[c for c in required if c not in data]
    if missing:
        raise ValueError("Missing CSV columns: "+", ".join(missing))
    data=data[list(required)].copy()
    data["date"]=pd.to_datetime(data["date"],errors="raise").dt.date
    for col in required[1:]:
        data[col]=pd.to_numeric(data[col],errors="raise")
    data=data.sort_values("date").drop_duplicates("date").reset_index(drop=True)
    if len(data)<95:
        raise ValueError(f"Need >=95 daily bars, got {len(data)}")
    if not ((data.high>=data[["open","close","low"]].max(axis=1)) &
            (data.low<=data[["open","close","high"]].min(axis=1))).all():
        raise ValueError("Invalid OHLC data")
    return data


def run(ticker, csv=None, fetch_live=False, output=None, check_tests=False):
    if check_tests:
        subprocess.run([sys.executable,"-m","unittest","discover",
                        "-s","tests","-v"],check=True)
    if bool(csv)==bool(fetch_live):
        raise ValueError("Choose exactly one input: --csv PATH or --fetch")
    data=load_csv(csv) if csv else fetch(ticker)
    if len(data)<95:
        raise ValueError(f"Need >=95 bars, got {len(data)}")
    data=indicators(data)
    output=Path(output or "quick_test_output").resolve()
    (output/"charts").mkdir(parents=True,exist_ok=True)
    old=engine.OUT
    try:
        engine.OUT=output
        chart(data,ticker,output/"charts"/f"{ticker}.png")
        marks=annotations(data)
        results=[{"symbol":ticker,"session_date":str(data.iloc[-1].date),
                  "candles":95,"annotations":marks}]
        render(results)
        (output/"results.json").write_text(
            json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    finally:
        engine.OUT=old
    print("QUICK_TEST_OK",ticker,"last_session",data.iloc[-1].date)
    print("MARKS",json.dumps(marks,ensure_ascii=False))
    print("OPEN",output/"index.html")


if __name__=="__main__":
    p=argparse.ArgumentParser(description="Fast Stage 1 HTML visual check")
    p.add_argument("--ticker",default="BE",help="Ticker to inspect, default BE")
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument("--csv",type=Path,help="Saved daily OHLCV CSV")
    group.add_argument("--fetch",action="store_true",help="Use private Massive API key")
    p.add_argument("--output",type=Path,default=Path("quick_test_output"))
    p.add_argument("--check-tests",action="store_true")
    args=p.parse_args()
    run(args.ticker.upper(),args.csv,args.fetch,args.output,args.check_tests)
