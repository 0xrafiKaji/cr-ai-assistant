import unittest
import os
import asyncio
from modules.academic.class_tracker import class_tracker
from modules.academic.assessment_planner import assessment_planner
from modules.academic.portal_scraper import portal_scraper
from modules.mailer.email_service import email_service
from core.gemini_brain import gemini_brain

class TestPhase4And5(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from modules.sheets.sync import sheet_sync
        from modules.sheets.models import FacultyMember
        sheet_sync.faculty_map["MN"] = FacultyMember(initial="MN", name="Md. Naim", email="naim@example.edu")
        try:
            sheet_sync.sync_all()
        except Exception:
            pass
    def test_01_class_tracker(self):
        """Test logging held and cancelled classes and getting formatted report."""
        log1 = class_tracker.log_class("EEE 1201", "MN", status="held", room="UB-110", notes="Ch 3 covered")
        log2 = class_tracker.log_class("CSE 1203", "FI", status="cancelled", room="1501", notes="Faculty meeting")
        self.assertGreater(log1, 0)
        self.assertGreater(log2, 0)

        report = class_tracker.get_history()
        self.assertIn("CLASS HISTORY LOG REPORT", report)
        self.assertIn("EEE 1201", report)
        self.assertIn("CSE 1203", report)

        export_path = class_tracker.export_csv("/tmp/test_class_export.csv")
        self.assertTrue(os.path.exists(export_path))
        if os.path.exists(export_path):
            os.remove(export_path)

    def test_02_assessment_planner(self):
        """Test logging CTs and generating a workload-balanced plan."""
        ass_id = assessment_planner.log_assessment("CSE 1203", "CT", number=1, status="completed", notes="Linked list")
        self.assertGreater(ass_id, 0)

        summary = assessment_planner.get_assessment_summary()
        self.assertIn("CSE 1203", summary)
        self.assertIn("CT-1", summary)

        # Generate workload-balanced schedule
        plan = assessment_planner.generate_balanced_plan(remaining_weeks=6)
        self.assertIsNotNone(plan)
        # Verify no broken Bengali unicode characters in plan
        has_bengali_script = any('\u0980' <= c <= '\u09FF' for c in plan)
        self.assertFalse(has_bengali_script, "Plan should not contain Bengali Unicode script to protect terminal font.")

    def tearDown(self):
        import sqlite3
        from core.database import DB_PATH
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("DELETE FROM class_history WHERE notes IN ('Ch 3 covered', 'Faculty meeting')")
            c.execute("DELETE FROM assessments WHERE notes = 'Linked list'")
            conn.commit()
            conn.close()
        except Exception:
            pass

    def test_03_attendance_scraper_and_alert(self):
        """Test attendance record checking and alert triggering for <75%."""
        from unittest.mock import patch
        mock_data = [
            {"course_code": "CSE 1201", "total_classes": 14, "attended_classes": 10, "absent_classes": 4, "percentage": 71.43, "last_checked": "2026-10-18", "absents": []},
            {"course_code": "CSE 1202", "total_classes": 14, "attended_classes": 12, "absent_classes": 2, "percentage": 85.71, "last_checked": "2026-10-18", "absents": []}
        ]
        with patch.object(portal_scraper, "get_latest_attendance", return_value=mock_data):
            records = portal_scraper.get_latest_attendance()
            self.assertGreater(len(records), 0)

            # Run alert check
            has_alert, alert_msg = asyncio.run(portal_scraper.check_and_alert_if_low())
            self.assertTrue(has_alert)
            self.assertIn("ATTENDANCE ALERT", alert_msg)
            self.assertIn("CSE 1201", alert_msg)

    def test_04_email_service_draft_and_approval(self):
        """Test resolving teacher email, drafting formal email, and sending with admin approval."""
        email_id, preview = email_service.draft_email(
            recipient_query="MN",
            topic="Request for CT 2 Syllabus and Schedule"
        )
        self.assertGreater(email_id, 0)
        self.assertIn("naim@example.edu", preview)
        self.assertIn("DRAFT EMAIL", preview)

        # Sending without approval should fail if status was not pending
        # Approve via command
        reply, is_fb = gemini_brain.process_query(
            sender_id="admin_test",
            sender_name="Admin",
            message=f"!sendmail {email_id}",
            is_admin=True
        )
        self.assertFalse(is_fb)
        self.assertIn("SENT successfully", reply)

if __name__ == "__main__":
    unittest.main()
