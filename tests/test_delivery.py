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
        ok,_,_=self.check("2026-07-07T02:10:00")
        self.assertFalse(ok)
    def test_backup_slot_in_summer(self):
        ok,day,_=self.check("2026-07-07T04:17:00")
        self.assertTrue(ok)
        self.assertEqual(day.isoformat(),"2026-07-06")
    def test_backup_slot_in_winter(self):
        ok,day,_=self.check("2026-01-06T05:17:00")
        self.assertTrue(ok)
        self.assertEqual(day.isoformat(),"2026-01-05")
    def test_delayed_schedule_still_delivers_in_winter(self):
        ok,day,reason=self.check("2026-10-27T06:30:00")
        self.assertTrue(ok,reason)
        self.assertEqual(day.isoformat(),"2026-10-26")
    def test_schedule_after_morning_window_skips(self):
        ok,_,_=self.check("2026-10-27T08:10:00")
        self.assertFalse(ok)
    def test_sent_marker_prevents_duplicate(self):
        from unittest.mock import patch
        from mail_report import already_sent
        class Dummy:
            pass
        with patch("mail_report.github_get",return_value={"artifacts":[
            {"name":"method20-sent-2026-10-26","expired":False}]}):
            self.assertTrue(already_sent(Dummy(),"owner/repo",
                datetime(2026,10,26).date()))
    def test_repeated_winter_morning_checks(self):
        for ts in ("2026-10-28T04:07:00","2026-10-28T04:27:00",
                   "2026-10-28T05:47:00","2026-10-28T07:47:00"):
            ok,day,reason=self.check(ts)
            self.assertTrue(ok,(ts,reason))
            self.assertEqual(day.isoformat(),"2026-10-27")
    def test_repeated_summer_morning_checks(self):
        for ts in ("2026-07-08T03:07:00","2026-07-08T03:47:00",
                   "2026-07-08T06:27:00"):
            ok,day,reason=self.check(ts)
            self.assertTrue(ok,(ts,reason))
            self.assertEqual(day.isoformat(),"2026-07-07")
    def test_holiday_skips(self):
        ok,_,_=self.check("2026-12-26T04:10:00")
        self.assertFalse(ok)
    def test_inline_html_email_with_chart_no_zip_attachment(self):
        results=[{"symbol":"MU",
                  "analysis":{"status":"READY","close":101.2,"sma20":99.5,
                              "cci14":32.1,"volume_ratio":1.2,
                              "change_5d_pct":3.1,"change_21d_pct":8.2,
                              "active":{"setup":"B: SMA20_BOUNCE","high":102,"low":98}},
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
        self.assertNotIn("ניתוח AI חזותי",msg.get_body(preferencelist=("html",)).get_content())
        self.assertIn("cid:method20-chart-0@local",msg.get_body(preferencelist=("html",)).get_content())
        self.assertFalse(any(p.get_filename() and p.get_filename().endswith(".zip")
                             for p in msg.walk()))
        self.assertTrue(any(p.get_content_type()=="image/jpeg" for p in msg.walk()))

    def test_recovery_requires_complete_artifact(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from mail_report import regenerate_missing_report
        import engine
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/"report.html").write_text("<html>report</html>")
            (root/"results.json").write_text(json.dumps([
                {"symbol":"MU","analysis":{"symbol_date":"2026-10-23"},
                 }]))
            (root/"metadata.json").write_text(json.dumps({
                "session_date":"2026-10-23","complete":True,
                "expected_ticker_count":1}))
            (root/"charts").mkdir()
            (root/"charts"/"MU.png").write_bytes(b"chart bytes")
            with patch.object(engine,"OUT",root),patch.object(engine,"main"):
                raw,results,url=regenerate_missing_report(
                    datetime(2026,10,23).date())
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                self.assertIn("metadata.json",z.namelist())
                self.assertIn("charts/MU.png",z.namelist())
            self.assertEqual(len(results),1)

    def test_recovery_rejects_incomplete_analysis(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from mail_report import regenerate_missing_report
        import engine
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/"metadata.json").write_text(json.dumps({
                "session_date":"2026-10-23","complete":False,
                "expected_ticker_count":1}))
            (root/"results.json").write_text(json.dumps([
                {"symbol":"MU","error":"missing bars"}]))
            with patch.object(engine,"OUT",root),patch.object(engine,"main"):
                with self.assertRaisesRegex(RuntimeError,"failed"):
                    regenerate_missing_report(datetime(2026,10,23).date())

    def test_missing_chart_fails_before_sending(self):
        result=[{"symbol":"MU","analysis":{"status":"READY"}}]
        archive=io.BytesIO()
        with zipfile.ZipFile(archive,"w") as z:
            z.writestr("results.json","[]")
        with self.assertRaisesRegex(ValueError,"Missing chart"):
            make_message(archive.getvalue(),result,datetime(2026,7,6).date(),
                         "https://github.com/test")

if __name__=="__main__":
    unittest.main()
