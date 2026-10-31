"""Stage 1 visual marking, without market-context or trade conditions."""
import unittest
import pandas as pd
from stage1_patterns import annotations

class StageOnePatternsTest(unittest.TestCase):
    def bars(self):
        dates=pd.date_range("2026-06-01",periods=110,freq="B")
        return pd.DataFrame([{"date":str(t.date()),"open":100.,
            "high":102.,"low":98.,"close":101.,"volume":100.,"sma20":115.}
            for t in dates])

    def test_stage2_close_below_sma20_is_accepted(self):
        d=self.bars()
        d.loc[109,["open","high","low","close","volume","sma20"]]=[
            102.,105.,94.,104.,101.,105.]
        self.assertIn("HAMMER",[p["pattern"] for p in annotations(d)])

    def test_stage2_low_between_sma20_and_102_percent_is_accepted(self):
        d=self.bars()
        d.loc[109,["open","high","low","close","volume","sma20"]]=[
            105.,106.,101.,105.,120.,100.]
        self.assertIn("REGULAR_DOJI",[p["pattern"] for p in annotations(d)])
        d.loc[109,"low"]=102.0
        self.assertIn("REGULAR_DOJI",[p["pattern"] for p in annotations(d)])

    def test_stage2_rejects_above_two_percent_or_dip_below_sma_without_close_below(self):
        d=self.bars()
        d.loc[109,["open","high","low","close","volume","sma20"]]=[
            105.,106.,103.,105.,120.,100.]
        self.assertFalse(annotations(d))
        d.loc[109,["open","high","low","close"]]=[105.,106.,99.,105.]
        self.assertFalse(annotations(d))

    def test_stage2_filters_complex_pattern_on_completion_candle_only(self):
        d=self.bars()
        d.loc[108,["open","high","low","close","sma20"]]=[108.,109.,100.,101.,100.]
        d.loc[109,["open","high","low","close","sma20"]]=[100.,111.,99.,110.,100.]
        self.assertNotIn("BULLISH_ENGULFING",[p["pattern"] for p in annotations(d)])
        d.loc[109,"sma20"]=115.
        self.assertIn("BULLISH_ENGULFING",[p["pattern"] for p in annotations(d)])

    def test_stage2_missing_sma20_never_marks_pattern(self):
        d=self.bars()
        d.loc[109,["open","high","low","close","volume","sma20"]]=[
            105.,106.,101.,105.,120.,float("nan")]
        self.assertFalse(annotations(d))

    def test_last_bar_green_and_red_hammer_need_above_previous_20_volume(self):
        for o,c in ((102.,104.),(104.,102.)):
            d=self.bars()
            d.loc[109,["open","high","low","close","volume"]]=[o,105.,94.,c,101.]
            labels=[x["pattern"] for x in annotations(d)]
            self.assertIn("HAMMER",labels)
            d.loc[109,"volume"]=100.
            self.assertNotIn("HAMMER",[x["pattern"] for x in annotations(d)])

    def test_regular_and_dragonfly_doji_final_only(self):
        d=self.bars()
        d.loc[109,["open","high","low","close","volume"]]=[100.,104.,96.,100.,110.]
        self.assertIn("REGULAR_DOJI",[x["pattern"] for x in annotations(d)])
        d.loc[109,["open","high","low","close"]]=[103.9,104.,95.,103.9]
        self.assertIn("DRAGONFLY_DOJI",[x["pattern"] for x in annotations(d)])
        d.loc[109,"volume"]=99.
        self.assertFalse(any(x["kind"]=="SINGLE" for x in annotations(d)))

    def test_two_bar_bullish_engulfing_no_volume_or_downtrend_filter(self):
        d=self.bars()
        d.loc[106,["open","high","low","close","volume"]]=[108.,109.,100.,101.,15.]
        d.loc[107,["open","high","low","close","volume"]]=[100.,111.,99.,110.,20.]
        found=[x for x in annotations(d) if x["pattern"]=="BULLISH_ENGULFING"]
        self.assertEqual(len(found),1)
        self.assertEqual((found[0]["start"],found[0]["end"]),(91,92))
        self.assertEqual(found[0]["kind"],"COMPLEX")

    def test_only_patterns_completed_in_last_five(self):
        d=self.bars()
        d.loc[102,["open","high","low","close"]]=[108.,109.,100.,101.]
        d.loc[103,["open","high","low","close"]]=[100.,111.,99.,110.]
        self.assertNotIn("BULLISH_ENGULFING",[x["pattern"] for x in annotations(d)])

    def test_newer_single_doji_replaces_older_complex_pattern(self):
        # BE-style example: an older valid engulfing and a newer last-day
        # high-volume Doji. Only the Doji is drawn.
        d=self.bars()
        d.loc[106,["open","high","low","close"]]=[108.,109.,100.,101.]
        d.loc[107,["open","high","low","close"]]=[100.,111.,99.,110.]
        d.loc[109,["open","high","low","close","volume"]]=[
            100.,104.,96.,100.,120.]
        marks=annotations(d)
        self.assertEqual(len(marks),1)
        self.assertEqual(marks[0]["pattern"],"REGULAR_DOJI")
        self.assertEqual(marks[0]["end"],94)

    def test_newest_complex_replaces_older_nonoverlapping_complex(self):
        d=self.bars()
        d.loc[104,["open","high","low","close"]]=[108.,109.,100.,101.]
        d.loc[105,["open","high","low","close"]]=[100.,111.,99.,110.]
        d.loc[108,["open","high","low","close"]]=[108.,109.,100.,101.]
        d.loc[109,["open","high","low","close"]]=[100.,111.,99.,110.]
        marks=annotations(d)
        self.assertEqual(len(marks),1)
        self.assertEqual(marks[0]["pattern"],"BULLISH_ENGULFING")
        self.assertEqual(marks[0]["end"],94)

    def test_invalid_newest_pattern_does_not_hide_older_valid_one(self):
        d=self.bars()
        d.loc[106,["open","high","low","close"]]=[108.,109.,100.,101.]
        d.loc[107,["open","high","low","close"]]=[100.,111.,99.,110.]
        d.loc[109,["open","high","low","close","volume","sma20"]]=[
            105.,106.,103.,105.,120.,100.]
        marks=annotations(d)
        self.assertEqual(len(marks),1)
        self.assertEqual(marks[0]["end"],92)

    def test_three_bar_pattern_preferred_to_overlapping_two_bar(self):
        d=self.bars()
        d.loc[107,["open","high","low","close"]]=[110.,111.,97.,98.]
        d.loc[108,["open","high","low","close"]]=[99.,108.,98.,107.]
        d.loc[109,["open","high","low","close"]]=[103.,114.,102.,113.]
        found=annotations(d)
        self.assertIn("THREE_INSIDE_UP",[x["pattern"] for x in found])
        self.assertEqual(sum(1 for x in found if x["end"]==94),1)

if __name__=="__main__":
    unittest.main()
