import unittest
import io
import zipfile
from PIL import Image
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
    def test_manual_friday_evening_uses_thursday_session(self):
        ok,day,_=self.check("2026-10-23T17:15:00","workflow_dispatch")
        self.assertTrue(ok)
        self.assertEqual(day.isoformat(),"2026-10-22")
    def test_scheduled_friday_evening_cannot_send_old_report(self):
        ok,_,_=self.check("2026-10-23T17:15:00","schedule")
        self.assertFalse(ok)
    def test_monday_morning_delivers_friday(self):
        ok,day,reason=self.check("2026-10-26T04:10:00")
        self.assertTrue(ok,reason)
        self.assertEqual(day.isoformat(),"2026-10-23")
    def test_monday_summer_delivers_friday(self):
        ok,day,reason=self.check("2026-07-13T03:10:00")
        self.assertTrue(ok,reason)
        self.assertEqual(day.isoformat(),"2026-07-10")
    def test_no_old_report_on_tuesday_morning(self):
        ok,day,_=self.check("2026-10-27T04:10:00")
        self.assertTrue(ok)
        self.assertEqual(day.isoformat(),"2026-10-26")
    def test_wrong_utc_slot_skips(self):
        ok,_,_=self.check("2026-07-07T04:10:00")
        self.assertFalse(ok)
    def test_holiday_skips(self):
        ok,_,_=self.check("2026-12-26T04:10:00")
        self.assertFalse(ok)
    def test_inline_html_email_with_chart_no_zip_attachment(self):
        results=[{"symbol":"MU",
                  "analysis":{"status":"READY","close":101.2,"sma20":99.5,
                              "cci14":32.1,"volume_ratio":1.2,
                              "change_5d_pct":3.1,"change_21d_pct":8.2,
                              "active":{"setup":"B: SMA20_BOUNCE","high":102,"low":98}},
                  "ai_review":{"status":"COMPLETE","text":"סקירה חזותית לדוגמה"},
                  "levels":{"support":[{"price":97}],"resistance":[{"price":105}]},
                  "outlook":{"bias":"נטייה שורית","reason":"עלייה",
                             "bull_case":"מעל התנגדות","bear_case":"מתחת לתמיכה"}}]
        im=Image.new("RGB",(80,60),"white")
        buf=io.BytesIO()
        im.save(buf,format="PNG")
        archive=io.BytesIO()
        with zipfile.ZipFile(archive,"w") as z:
            z.writestr("charts/MU.png",buf.getvalue())
        msg=make_message(archive.getvalue(),results,
                         datetime(2026,7,6).date(),"https://github.com/test")
        self.assertEqual(msg["To"],"Haimboch@gmail.com")
        self.assertIn("2026-07-06",msg["Subject"])
        self.assertIn("סקירה חזותית לדוגמה",msg.get_body(preferencelist=("html",)).get_content())
        self.assertIn("cid:method20-chart-0@local",msg.get_body(preferencelist=("html",)).get_content())
        self.assertFalse(any(p.get_filename() and p.get_filename().endswith(".zip")
                             for p in msg.walk()))
        self.assertTrue(any(p.get_content_type()=="image/jpeg" for p in msg.walk()))

    def test_missing_chart_fails_before_sending(self):
        result=[{"symbol":"MU","analysis":{"status":"READY"},"ai_review":{"text":"ok"}}]
        archive=io.BytesIO()
        with zipfile.ZipFile(archive,"w") as z:
            z.writestr("results.json","[]")
        with self.assertRaisesRegex(ValueError,"Missing chart"):
            make_message(archive.getvalue(),result,datetime(2026,7,6).date(),
                         "https://github.com/test")

if __name__=="__main__":
    unittest.main()
