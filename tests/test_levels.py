import unittest
import pandas as pd
from levels import structure, scenario

class LevelsTests(unittest.TestCase):
    def sample(self):
        rows=[]
        for i in range(90):
            base=100+(i%14-7)*0.5
            rows.append({"date":f"2026-{(i//28)+1:02d}-{(i%28)+1:02d}",
                         "open":base-.15,"high":base+1,"low":base-1,
                         "close":base+.2,"volume":100+i%5,
                         "sma20":100.0,"cci":10})
        return pd.DataFrame(rows)
    def test_levels_ordered_around_close(self):
        d=self.sample()
        lv=structure(d)
        self.assertTrue(all(x["price"]<lv["price"] for x in lv["support"]))
        self.assertTrue(all(x["price"]>lv["price"] for x in lv["resistance"]))
    def test_lookback_and_max_two_levels(self):
        lv=structure(self.sample())
        self.assertLessEqual(len(lv["support"]),2)
        self.assertLessEqual(len(lv["resistance"]),2)
    def test_outlook_contains_both_scenarios(self):
        d=self.sample()
        o=scenario(d,structure(d))
        self.assertIn(o["bias"],("נטייה שורית","נטייה דובית","מעורב / ללא הכרעה"))
        self.assertTrue(o["bull_case"])
        self.assertTrue(o["bear_case"])
        self.assertIn("מותנים",o["note"])
    def test_minimum_data(self):
        with self.assertRaises(ValueError):
            structure(self.sample().head(5))

if __name__=="__main__":unittest.main()
