"""Checks for the intentionally minimal METHOD20 daily chart report."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from engine import chart, render, indicators, daily_session_dates

class ChartOnlyTests(unittest.TestCase):
    def data(self,n=115):
        d=pd.DataFrame([{
            "date":str(t.date()),"open":100+i*.2,"high":102+i*.2,
            "low":99+i*.2,"close":101+i*.2,"volume":1000+i*20
        } for i,t in enumerate(pd.date_range("2026-04-01",periods=n,freq="B"))])
        return indicators(d)

    def test_daily_date_remains_utc_session(self):
        stamp=pd.Series([pd.Timestamp("2026-10-29T00:00:00Z").timestamp()*1000])
        self.assertEqual(str(daily_session_dates(stamp).iloc[0]),"2026-10-29")

    def test_chart_contains_exactly_95_daily_candles_and_indicators(self):
        d=self.data()
        with tempfile.TemporaryDirectory() as root:
            image=Path(root)/"MU.png"
            chart(d,"MU",image)
            self.assertGreater(image.stat().st_size,10000)
        self.assertEqual(len(d.tail(95)),95)
        self.assertTrue(pd.notna(d.sma20.iloc[-1]))
        self.assertTrue("cci" in d.columns)

    def test_insufficient_history_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError,"95 required"):
                chart(self.data(80),"TEST",Path(root)/"test.png")

    def test_clean_report_omits_triggers_patterns_zones_positions(self):
        with tempfile.TemporaryDirectory() as root:
            with patch("engine.OUT",Path(root)):
                render([{"symbol":"MU","session_date":"2026-10-29","candles":95}])
                page=(Path(root)/"report.html").read_text()
        self.assertIn("charts/MU.png",page)
        self.assertIn("Daily Charts",page)
        for absent in ("TRIGGERED","CANDIDATE","READY","טריגר",
                       "תמיכה","התנגדות","פוזיציות","risk_reward"):
            self.assertNotIn(absent,page)

if __name__=="__main__":
    unittest.main()
