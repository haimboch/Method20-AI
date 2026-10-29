import unittest
import pandas as pd
from report_format import fmt2, fmt_signed, format_numbers_in_text
from levels import structure
from engine import visible_bullish_patterns, reversal_for_chart
from report_sections import grouped_results, signal_explanation, signal_for_display

class ReportPresentationTests(unittest.TestCase):
    def test_two_candle_engulfing_is_recent_only(self):
        d=pd.DataFrame([{"date":str(i),"open":10.0,"high":11.0,
            "low":9.5,"close":10.8,"sma20":8.00} for i in range(20)])
        d.loc[18:19,"sma20"]=11.0
        d.loc[18,["open","close"]]=[10.8,10.0]
        d.loc[19,["open","high","low","close"]]=[9.9,11.4,9.7,11.2]
        patterns=visible_bullish_patterns(d)
        self.assertEqual(patterns[-1]["pattern"],"BULLISH_ENGULFING")
        self.assertEqual((patterns[-1]["start"],patterns[-1]["end"]),(18,19))
        self.assertEqual(len(visible_bullish_patterns(d.iloc[:-10])),0)
        d["sma20"]=8.00
        self.assertEqual(visible_bullish_patterns(d),[])

    def test_recent_doji_only_when_below_or_touching_sma20(self):
        d=pd.DataFrame([{"date":str(i),"open":10,"close":10,
                         "high":10.6,"low":9.5,"sma20":10.2}
                        for i in range(12)])
        self.assertTrue(any(x["pattern"]=="DOJI" for x in visible_bullish_patterns(d)))
        d["sma20"]=8
        self.assertEqual(visible_bullish_patterns(d),[])

    def test_signal_marker_uses_ready_and_finished_events(self):
        d=pd.DataFrame({"date":["2026-10-26","2026-10-27"]})
        signal={"signal_date":"2026-10-26","high":101.25,"low":98.0,"status":"READY"}
        self.assertEqual(reversal_for_chart({"active":signal},d)[0],0)
        self.assertEqual(reversal_for_chart({"last_event":dict(signal,status="TRIGGERED")},d)[0],0)
        self.assertIsNone(reversal_for_chart({"last_event":dict(signal,status="BROKEN")},d))
        self.assertIsNone(reversal_for_chart({"last_event":dict(signal,status="INVALIDATED")},d))
        self.assertIsNone(reversal_for_chart({"active":{"signal_date":"2026-10-20"}},d))

    def test_report_groups_ready_triggered_then_other(self):
        signal={"status":"READY","setup":"B: SMA20_BOUNCE","pattern":"HAMMER",
                "signal_date":"2026-10-28","high":110.0,"low":101.0}
        rows=[
            {"symbol":"NONE","analysis":{"status":"NO ACTIVE SETUP"}},
            {"symbol":"TRIG","analysis":{"status":"TRIGGERED",
                 "last_event":dict(signal,status="TRIGGERED")}},
            {"symbol":"READY","analysis":{"status":"READY","active":signal}},
            {"symbol":"BROKEN","analysis":{"status":"BROKEN",
                 "last_event":dict(signal,status="BROKEN")}},
        ]
        groups=grouped_results(rows)
        self.assertEqual([k for k,_,_ in groups],["READY","TRIGGERED","OTHER"])
        self.assertEqual([[r["symbol"] for r in group] for _,_,group in groups],
                         [["READY"],["TRIG"],["NONE","BROKEN"]])
        self.assertEqual(signal_for_display(rows[2])["high"],110.0)
        self.assertIsNone(signal_for_display(rows[3]))
        self.assertIn("SMA20",signal_explanation(signal))

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
