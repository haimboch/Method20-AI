import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from engine import chart,render
from method20_zones import update_book,chosen_zone,risk_reward

class ReportTests(unittest.TestCase):
    def test_chart_has_candles_volume_cci_and_overlay(self):
        d=pd.DataFrame([{"date":f"2026-10-{i+1:02d}","open":100+i*.2,
               "high":101+i*.2,"low":99+i*.2,"close":100.5+i*.2,
               "sma20":100+i*.1,"volume":1000+i*20,"cci":float(i)}
              for i in range(24)])
        signal={"status":"CANDIDATE","setup":"A: MEAN_REVERSION",
                "pattern":"HAMMER","start_date":str(d.date.iloc[-1]),
                "signal_date":str(d.date.iloc[-1]),"high":106,"low":103}
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"chart.png"
            chart(d,"TEST",path,{"active":signal},None)
            self.assertGreater(path.stat().st_size,1000)

    def test_minimal_html_and_risk_ratio(self):
        signal={"status":"READY","setup":"B: SMA20_BOUNCE",
                "pattern":"HAMMER","start_date":"2026-10-01",
                "signal_date":"2026-10-01","high":105,"low":100}
        row={"symbol":"TEST","analysis":{"active":signal,"status":"READY"},
             "risk_reward":2}
        with tempfile.TemporaryDirectory() as root:
            with patch("engine.OUT",Path(root)):
                render([row])
                page=(Path(root)/"report.html").read_text()
        self.assertIn("TEST",page)
        self.assertIn("charts/TEST.png",page)
        self.assertIn("טריגר",page)
        self.assertNotIn("צ׳קליסט",page)

    def test_two_daily_closes_required_for_zone_break(self):
        d=pd.DataFrame([{"date":f"2026-10-{i+1:02d}","open":101,
             "high":102,"low":99,"close":101,"volume":1000,
             "sma20":101} for i in range(22)])
        z={"kind":"support","low":100,"high":102,"status":"ACTIVE",
           "score":80,"created_at":"2026-10-01"}
        d.loc[20,"close"]=99;d.loc[21,"close"]=101
        book=update_book(d,{"support":z},None,None)
        self.assertNotEqual(book["support"]["status"],"WAITING_RETEST")
        d.loc[21,"close"]=98
        book=update_book(d,{"support":z},None,None)
        self.assertEqual(book["support"]["status"],"WAITING_RETEST")

    def test_support_is_hidden_when_price_moves_below_it(self):
        d=pd.DataFrame([{"date":f"2026-10-{i+1:02d}","open":100,
            "high":101,"low":97,"close":99,"volume":1000,
            "sma20":100} for i in range(22)])
        # Only one close below the zone; should not mark it broken.
        d.loc[20,"close"]=101
        zone={"kind":"support","low":100,"high":102,"status":"ACTIVE",
              "score":90,"created_at":"2026-10-01"}
        book=update_book(d,{"support":zone},"support",99)
        from method20_zones import zone_is_relevant
        visible=chosen_zone(book,"support")
        self.assertTrue(visible is None or zone_is_relevant(visible,"support",99))

    def test_resistance_must_be_above_original_trigger(self):
        d=pd.DataFrame([{"date":f"2026-10-{i+1:02d}","open":103,
            "high":105,"low":101,"close":103,"volume":1000,
            "sma20":103} for i in range(22)])
        zone={"kind":"resistance","low":100,"high":104,"status":"ACTIVE",
              "score":90,"created_at":"2026-10-01"}
        book=update_book(d,{"resistance":zone},"resistance",105)
        visible=chosen_zone(book,"resistance")
        self.assertTrue(visible is None or visible["low"]>105)

    def test_rr_is_information(self):
        self.assertEqual(risk_reward({"high":105,"low":100},
                                    {"low":115,"high":117}),2)

if __name__=="__main__":unittest.main()
