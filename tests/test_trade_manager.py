import json
import tempfile
import unittest
from pathlib import Path
from trade_manager import add_event,load,replay,report_rows

class TradeLedgerTests(unittest.TestCase):
    def event(self,action,**fields):
        return {"action":action,"symbol":"XYZ","date":"2026-10-20",**fields}

    def test_buy_no_pyramiding_and_no_lowering_stop(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"ledger.json"
            add_event(path,self.event("BUY",quantity=50,price=100,stop=95))
            with self.assertRaises(ValueError):
                add_event(path,self.event("BUY",quantity=10,price=110,stop=100))
            with self.assertRaises(ValueError):
                add_event(path,self.event("UPDATE_STOP",stop=94))
            self.assertEqual(len(load(path)),1)
            add_event(path,self.event("UPDATE_STOP",stop=101))
            positions,_,_=replay(load(path))
            self.assertEqual(positions["XYZ"]["stop"],101)

    def test_partials_and_close(self):
        events=[
          self.event("BUY",quantity=100,price=50,stop=47),
          self.event("SELL_PARTIAL",quantity=30,price=55),
          self.event("SELL_PARTIAL",quantity=20,price=60),
        ]
        p,_,_=replay(events)
        self.assertEqual(p["XYZ"]["quantity"],50)
        self.assertEqual(p["XYZ"]["realized"],350)
        events.append(self.event("CLOSE",price=62))
        p,closed,_=replay(events)
        self.assertEqual(p,{})
        self.assertEqual(closed[-1]["realized"],950)

    def test_skip_signal_date(self):
        _,_,closed=replay([self.event("SKIP_TRADE",signal_date="2026-10-19")])
        self.assertEqual(closed["XYZ"],{"2026-10-19"})

    def test_stop_alert_not_retroactive(self):
        events=[self.event("BUY",quantity=10,price=100,stop=95),
                self.event("UPDATE_STOP",stop=105,date="2026-10-22")]
        day={"XYZ":{"date":"2026-10-23","close":110,"low":104}}
        rows,alerts=report_rows(events,day)
        self.assertEqual(alerts[0]["stop"],105)
        self.assertEqual(rows[0]["risk_to_stop"],50)

if __name__=="__main__":unittest.main()
