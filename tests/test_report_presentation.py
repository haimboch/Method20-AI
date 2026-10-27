import unittest
import pandas as pd
from report_format import fmt2, fmt_signed, format_numbers_in_text
from levels import structure

class ReportPresentationTests(unittest.TestCase):
    def test_numbers_are_two_decimals(self):
        self.assertEqual(fmt2(123.45678),"123.46")
        self.assertEqual(fmt_signed(-12.345),"-12.35")
        self.assertEqual(format_numbers_in_text("CCI: 123.4567 | volume: 1.2345x"),
                         "CCI: 123.46 | volume: 1.23x")
    def test_visible_chart_has_single_zone_per_side(self):
        rows=[]
        for i in range(120):
            price=100+(i%15-7)*0.8
            rows.append({"close":price,"open":price-0.1,
                         "high":price+1,"low":price-1,
                         "volume":1000,"sma20":100,"cci":0})
        d=pd.DataFrame(rows)
        result=structure(d,lookback=95)
        self.assertEqual(result["lookback"],95)
        self.assertLessEqual(len(result["support"]),1)
        self.assertLessEqual(len(result["resistance"]),1)
        for side in ("support","resistance"):
            for zone in result[side]:
                self.assertLess(zone["low"],zone["high"])
                self.assertLessEqual(zone["low"],zone["price"])
                self.assertGreaterEqual(zone["high"],zone["price"])

if __name__=="__main__":
    unittest.main()
