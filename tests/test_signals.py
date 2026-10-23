import unittest
from types import SimpleNamespace
import pandas as pd
from signals import transition, classify, candle_pattern, cci_upturn

class StateTests(unittest.TestCase):
    def setUp(self):
        self.s={"setup":"A: MEAN_REVERSION","signal_date":"2026-10-01",
                "high":101.0,"low":95.0,"status":"READY"}
    def day(self,date,high=100,low=96):
        return SimpleNamespace(date=date,high=high,low=low)
    def test_signal_day_not_trigger(self):
        self.assertEqual(transition(self.s,self.day("2026-10-01",110,90))["status"],"READY")
    def test_high_break(self):
        self.assertEqual(transition(self.s,self.day("2026-10-02",101.01))["status"],"TRIGGERED")
    def test_low_break(self):
        self.assertEqual(transition(self.s,self.day("2026-10-02",100,94.99))["status"],"INVALIDATED")
    def test_both_crossed_is_ambiguous(self):
        self.assertEqual(transition(self.s,self.day("2026-10-02",102,94))["status"],"AMBIGUOUS")
    def test_equal_level_no_break(self):
        self.assertEqual(transition(self.s,self.day("2026-10-02",101,95))["status"],"READY")
    def test_no_time_expiry(self):
        self.assertEqual(transition(self.s,self.day("2027-12-15"))["status"],"READY")
    def test_finished_event_not_retriggered(self):
        done=transition(self.s,self.day("2026-10-02",102))
        self.assertEqual(transition(done,self.day("2026-10-03",100,90))["status"],"TRIGGERED")

class SignalTests(unittest.TestCase):
    def data(self,oversold=False,volume=250):
        dates=pd.date_range("2026-08-01",periods=30,freq="B")
        d=pd.DataFrame([{"date":str(x.date()),"open":101.0,"high":102.0,
                         "low":99.5,"close":100.0,"volume":100.0,"sma20":100.0,
                         "vol20":100.0,"cci":0.0} for x in dates])
        d.loc[26,"cci"]=-130 if oversold else 20
        d.loc[27,"cci"]=30
        d.loc[28,"cci"]=10
        d.loc[29,["open","high","low","close","volume","cci"]]=[99.3,101.2,99.0,100.8,volume,40]
        return d
    def test_b_cci_not_oversold(self):
        d=self.data(False)
        s=classify(d,29)
        self.assertIsNotNone(s)
        self.assertEqual(s["setup"],"B: SMA20_BOUNCE")
    def test_volume_required(self):
        d=self.data(False,50)
        self.assertIsNone(classify(d,29))
    def test_cci_upturn_required(self):
        d=self.data(False)
        d.loc[28,"cci"]=45
        self.assertIsNone(classify(d,29))
    def test_doji_not_bullish(self):
        d=self.data()
        d.loc[29,["open","close","high","low"]]=[100,100,101,99]
        self.assertIsNone(candle_pattern(d,29))
    def test_hammer(self):
        d=self.data()
        d.loc[29,["open","close","high","low"]]=[100,100.4,100.5,98.4]
        self.assertEqual(candle_pattern(d,29),"HAMMER")

if __name__=="__main__": unittest.main()
