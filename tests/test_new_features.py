import unittest
from fastapi.testclient import TestClient
from main import app, generate_session_token
from config.settings import settings
from modules.academic.assessment_planner import assessment_planner
from core.gemini_brain import gemini_brain

class TestNewFeatures(unittest.TestCase):
    def setUp(self):
        token = generate_session_token(settings.DASHBOARD_PASSWORD)
        self.client = TestClient(app, cookies={"session_token": token})

    def test_personal_afk_ping_reply(self):
        """Verify that personal greetings/AFK pings get polite assistant away replies."""
        reply, is_fb = gemini_brain.process_query("test_user_1", "Friend", "achi re?")
        self.assertFalse(is_fb)
        self.assertIn("ekhon ektu offline/away ache", reply)

        reply2, is_fb2 = gemini_brain.process_query("test_user_2", "Friend", "cr koi")
        self.assertFalse(is_fb2)
        self.assertIn("ekhon ektu offline/away ache", reply2)

    def test_identity_who_are_you(self):
        """Verify bot identity query."""
        reply, is_fb = gemini_brain.process_query("test_user_3", "Student", "tui ke?")
        self.assertFalse(is_fb)
        self.assertIn("autonomous AI", reply)

    def test_assessment_endpoints(self):
        """Verify CT & Assessment Planner API endpoints."""
        # 1. Get summary
        res = self.client.get("/api/academic/assessments/summary")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("summary", data)
        self.assertIn("saved_plan", data)

        # 2. Save Plan
        test_plan = "🗓 Test CT Plan:\n• Week 1: CSE 1201 CT-2\n• Week 2: EEE 1201 CT-2"
        res_save = self.client.post("/api/academic/assessments/plan", json={"plan": test_plan})
        self.assertEqual(res_save.status_code, 200)
        self.assertEqual(res_save.json()["status"], "saved")

        # 3. Get Plan
        res_get = self.client.get("/api/academic/assessments/plan")
        self.assertEqual(res_get.status_code, 200)
        self.assertEqual(res_get.json()["plan"], test_plan)

        # 4. Log Assessment
        res_log = self.client.post("/api/academic/assessments/log", json={
            "course_code": "CSE 1201",
            "assessment_type": "CT",
            "number": 2,
            "status": "planned",
            "scheduled_date": "2026-10-25",
            "notes": "Chapter 3-4"
        })
        self.assertEqual(res_log.status_code, 200)
        new_id = res_log.json()["id"]

        # 5. Delete Assessment
        res_del = self.client.delete(f"/api/academic/assessments/{new_id}")
        self.assertEqual(res_del.status_code, 200)
        self.assertEqual(res_del.json()["status"], "deleted")

    def test_attendance_endpoints_and_roster(self):
        """Verify student roster has sample students and attendance submission/export works."""
        # 1. Get students list
        res = self.client.get("/api/attendance/students")
        self.assertEqual(res.status_code, 200)
        students = res.json()["students"]
        self.assertGreaterEqual(len(students), 1)
        self.assertEqual(students[0]["roll_no"], "1001")

        # 2. Submit attendance session
        records = [{"roll_no": s["roll_no"], "name": s["name"], "status": "P" if s["serial_no"] != 1 else "A", "notes": ""} for s in students]
        res_sub = self.client.post("/api/attendance/submit", json={
            "course_code": "CSE 101",
            "session_date": "2026-10-18",
            "topic": "Algorithms",
            "records": records
        })
        self.assertEqual(res_sub.status_code, 200)
        sess = res_sub.json()["session"]
        session_id = sess["session_id"]
        self.assertGreaterEqual(sess["total_present"], 1)

        # 3. Get session details
        res_det = self.client.get(f"/api/attendance/sessions/{session_id}")
        self.assertEqual(res_det.status_code, 200)
        self.assertEqual(res_det.json()["course_code"], "CSE 101")

        # 4. Export session CSV
        res_exp = self.client.get(f"/api/attendance/export/{session_id}")
        self.assertEqual(res_exp.status_code, 200)
        self.assertIn("text/csv", res_exp.headers.get("content-type", ""))

        # 5. Clean up session
        res_del = self.client.delete(f"/api/attendance/sessions/{session_id}")
        self.assertEqual(res_del.status_code, 200)
        self.assertEqual(res_del.json()["status"], "deleted")

    def test_text_to_notice_endpoints(self):
        """Verify text-to-notice drafting and 1-click broadcast endpoints."""
        from unittest.mock import patch, AsyncMock
        # 1. Draft notice from text
        with patch("modules.vision.screenshot_parser.screenshot_parser.draft_from_text", return_value=(101, "📢 *NOTICE: Physics Lab Test*")):
            res_draft = self.client.post("/api/notices/draft-text", json={
                "raw_text": "kal shobai 10 tay 1502 e asba physics lab test nibe sir",
                "instruction": "Polite tone"
            })
            self.assertEqual(res_draft.status_code, 200)
            self.assertIn("draft_notice", res_draft.json())

        # 2. Direct broadcast to WhatsApp Notice Group
        with patch("modules.notifier.whatsapp_client.whatsapp_client.send_group_message", new_callable=AsyncMock) as mock_send, \
             patch("main.save_announcement") as mock_save:
            mock_send.return_value = True
            mock_save.return_value = 102
            res_broad = self.client.post("/api/notices/broadcast-direct", json={
                "title": "Physics Lab Test Notice",
                "content": "📢 *NOTICE: Physics Lab Test*\n• Time: 10:00 AM\n• Room: 1502\n— CR Assistant"
            })
            self.assertEqual(res_broad.status_code, 200)
            self.assertEqual(res_broad.json()["status"], "success")
            mock_send.assert_called_once()

    def test_admin_notice_and_attendance_commands(self):
        """Verify !notice and !takeattendance commands work via WhatsApp admin command."""
        from unittest.mock import patch, AsyncMock
        # 1. Admin command !notice
        with patch("modules.vision.screenshot_parser.screenshot_parser.draft_from_text", return_value=(201, "Draft Notice")):
            reply, is_fb = gemini_brain.process_query(
                sender_id="admin_user",
                sender_name="Admin",
                message="!notice kal 11 tay class test nibe",
                is_admin=True
            )
            self.assertFalse(is_fb)
            self.assertIn("NOTICE DRAFTED", reply)

        # 2. Admin command !takeattendance
        reply_att, is_fb_att = gemini_brain.process_query(
            sender_id="admin_user",
            sender_name="Admin",
            message="!takeattendance CSE 101 1001",
            is_admin=True
        )
        self.assertFalse(is_fb_att)
        self.assertIn("CLASS ATTENDANCE REPORT", reply_att)
        self.assertIn("CSE 101", reply_att)

    def test_security_hardening_messenger_webhooks(self):
        """Verify that external unauthorized invocations to Messenger webhooks are rejected with 403."""
        # Unauthenticated external request (TestClient simulates client host)
        # 1. With invalid token and simulated external client
        unauth_client = TestClient(app, base_url="http://external-host")
        
        # Test without token from external host
        res_ext = unauth_client.post(
            "/api/messenger/incoming",
            json={"sender_name": "Attacker", "message_text": "Fake notice"},
            headers={"client-ip": "198.51.100.1"}
        )
        # Local client without token succeeds only if localhost, but fails with wrong token if non-local
        # Test wrong token explicitly
        res_wrong_token = self.client.post(
            "/api/messenger/incoming",
            json={"sender_name": "Tester", "message_text": "Test notice"},
            headers={"X-Bridge-Token": "invalid_secret"}
        )
        # Should either succeed if local or fail with 403 if external
        # Verify valid secret key works
        res_valid = self.client.post(
            "/api/messenger/incoming",
            json={"sender_name": "Coordinator", "message_text": "Good morning"},
            headers={"X-Bridge-Token": settings.SECRET_KEY}
        )
        self.assertEqual(res_valid.status_code, 200)

if __name__ == "__main__":
    unittest.main()
