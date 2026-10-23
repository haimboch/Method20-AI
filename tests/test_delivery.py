import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from mail_report import delivery_decision, make_message

UTC=ZoneInfo("UTC")

class DeliveryTests(unittest.TestCase):
    def check(self,utc_text,event="schedule"):
        return delivery_decision(event,datetime.fromisoformat(utc_text).replace(tzinfo=UTC))
    def test_summer_morning(self):
        ok,day,_=self.check("2026-07-07T03:10:00")
        self.assertTrue(ok)
        self.assertEqual(day.isoformat(),"2026-07-06")
    def test_winter_morning(self):
        ok,day,_=self.check("2026-01-06T04:10:00")
        self.assertTrue(ok)
        self.assertEqual(day.isoformat(),"2026-01-05")
    def test_us_israel_dst_gap(self):
        ok,day,_=self.check("2026-10-27T04:10:00")
        self.assertTrue(ok)
        self.assertEqual(day.isoformat(),"2026-10-26")
    def test_wrong_utc_slot_skips(self):
        ok,_,_=self.check("2026-07-07T04:10:00")
        self.assertFalse(ok)
    def test_holiday_skips(self):
        ok,_,_=self.check("2026-12-26T04:10:00")
        self.assertFalse(ok)
    def test_mail_attachment_and_recipient(self):
        r=[{"symbol":"MU","analysis":{"status":"READY"}}]
        m=make_message(b"123",r,datetime(2026,7,6).date(),"https://github.com/test")
        self.assertEqual(m["To"],"Haimboch@gmail.com")
        self.assertIn("2026-07-06",m["Subject"])
        self.assertEqual(len(list(m.iter_attachments())),1)

if __name__=="__main__":
    unittest.main()
