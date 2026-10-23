import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from schedule_guard import decide

UTC=ZoneInfo("UTC")

class ScheduleTests(unittest.TestCase):
    def at(self,text,event="schedule"):
        return decide(event,datetime.fromisoformat(text).replace(tzinfo=UTC))
    def test_israel_summer_slot(self):
        x=self.at("2026-07-06T20:40:00")
        self.assertTrue(x["run"],x)
    def test_israel_winter_slot(self):
        x=self.at("2026-01-05T21:40:00")
        self.assertTrue(x["run"],x)
    def test_winter_extra_slot_skips(self):
        self.assertFalse(self.at("2026-01-05T20:40:00")["run"])
    def test_summer_extra_slot_skips(self):
        self.assertFalse(self.at("2026-07-06T21:40:00")["run"])
    def test_weekend_skips(self):
        self.assertFalse(self.at("2026-07-04T20:40:00")["run"])
    def test_us_holiday_skips(self):
        self.assertFalse(self.at("2026-12-25T21:40:00")["run"])
    def test_manual_allowed(self):
        self.assertTrue(self.at("2026-07-04T20:40:00","workflow_dispatch")["run"])

if __name__=="__main__":
    unittest.main()
