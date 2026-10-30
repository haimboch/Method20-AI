import unittest
import pandas as pd
from signals import candidate,confirmation,classify,transition,analyze,sma20_context
from patterns_method20 import detect_at

class Method20Tests(unittest.TestCase):
    def data(self):
        dates=pd.date_range("2026-08-01",periods=35,freq="B")
        d=pd.DataFrame([{"date":str(x.date()),"open":112,"close":110,
           "high":114,"low":108,"volume":100,"sma20":120,
           "vol20":100,"cci":-20} for x in dates])
        d.loc[24,"close"]=115
        d.loc[29,"close"]=105
        d.loc[32,"cci"]=-145
        d.loc[33,"cci"]=-160
        d.loc[34,["open","close","high","low","cci","volume"]]=[103,104,105,98,-120,180]
        return d

    def test_reversal_candle_and_context(self):
        d=self.data()
        self.assertEqual(detect_at(d,34)["pattern"],"HAMMER")
        self.assertTrue(sma20_context(d,34))
        c=candidate(d,34)
        self.assertEqual(c["status"],"CANDIDATE")
        self.assertEqual(c["setup"],"A: MEAN_REVERSION")

    def test_cci_volume_confirmation(self):
        d=self.data()
        self.assertTrue(confirmation(d,34,candidate(d,34)))
        self.assertEqual(classify(d,34)["status"],"READY")
        d.loc[34,"volume"]=40
        self.assertFalse(confirmation(d,34,candidate(d,34)))

    def test_red_hammer_and_doji(self):
        d=self.data()
        d.loc[34,["open","close","high","low"]]=[104,103,105,98]
        self.assertEqual(detect_at(d,34)["pattern"],"HAMMER")
        d.loc[34,["open","close","high","low"]]=[102,102,104,100]
        self.assertEqual(detect_at(d,34)["pattern"],"DOJI")

    def test_fixed_trigger_and_one_day_boundary(self):
        signal={"signal_date":"2026-10-01","high":105,"low":99,
                "status":"READY"}
        class Day:pass
        day=Day();day.date="2026-10-01";day.high=106;day.low=98
        self.assertEqual(transition(signal,day)["status"],"READY")
        day.date="2026-10-02"
        self.assertEqual(transition(signal,day)["status"],"AMBIGUOUS")
        day.low=100
        self.assertEqual(transition(signal,day)["status"],"TRIGGERED")
        day.high=104;day.low=100;day.date="2027-12-01"
        self.assertEqual(transition(signal,day)["status"],"READY")

    def test_candidate_expiration(self):
        d=self.data()
        d.loc[34,"volume"]=40
        a=analyze(d)
        self.assertIn(a["status"],("CANDIDATE","NO ACTIVE SETUP"))

if __name__=="__main__":unittest.main()
