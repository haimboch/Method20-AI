"""Stage 1 dashboard/quick-check tests without network or GitHub Actions."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd

from engine import render, indicators
import engine
from quick_test import load_csv, run


class DashboardQuickTests(unittest.TestCase):
    def fixture(self,n=115):
        return pd.DataFrame([
            {"date":str(day.date()),"open":100+i*.05,"high":102+i*.05,
             "low":99+i*.05,"close":101+i*.05,"volume":1000+i*10}
            for i,day in enumerate(pd.date_range("2026-04-01",periods=n,freq="B"))])

    def test_interactive_dashboard_contains_ticker_selector_and_session_dates(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(engine,"OUT",Path(tmp)):
                render([{"symbol":"BE","session_date":"2026-10-30",
                         "annotations":[{"pattern":"HAMMER"}]},
                        {"symbol":"MU","session_date":"2026-10-30",
                         "annotations":[]}])
            page=(Path(tmp)/"index.html").read_text(encoding="utf-8")
            self.assertEqual(page,(Path(tmp)/"report.html").read_text(encoding="utf-8"))
            for fragment in ('id="ticker"','id="search"','id="filter"',
                             "charts/","2026-10-30","HAMMER","SMA20"):
                self.assertIn(fragment,page)
            self.assertNotIn("MASSIVE_API_KEY",page)

    def test_quick_test_from_saved_csv_without_secrets_or_email(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp)
            csv=tmp/"BE.csv"
            self.fixture().to_csv(csv,index=False)
            self.assertEqual(len(load_csv(csv)),115)
            run("BE",csv=csv,output=tmp/"site")
            self.assertTrue((tmp/"site"/"index.html").is_file())
            self.assertGreater((tmp/"site"/"charts"/"BE.png").stat().st_size,10000)
            result=json.loads((tmp/"site"/"results.json").read_text(encoding="utf-8"))
            self.assertEqual(result[0]["symbol"],"BE")
            self.assertEqual(result[0]["candles"],95)

    def test_csv_rejects_insufficient_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv=Path(tmp)/"few.csv"
            self.fixture(80).to_csv(csv,index=False)
            with self.assertRaisesRegex(ValueError,"95"):
                load_csv(csv)

if __name__=="__main__":
    unittest.main()
