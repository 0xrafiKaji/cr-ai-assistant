import unittest
from fastapi.testclient import TestClient
from main import app, generate_session_token
from config.settings import settings
from core.gemini_brain import gemini_brain
from core.quota_tracker import quota_tracker

class TestQuotaAndPlans(unittest.TestCase):
    def setUp(self):
        token = generate_session_token(settings.DASHBOARD_PASSWORD)
        self.client = TestClient(app, cookies={"session_token": token})

    def test_quota_tracker_stats(self):
        """Verify quota tracker calculates percentage, remaining, and human reset time."""
        stats = quota_tracker.get_usage_stats()
        self.assertIn("percentage_used", stats)
        self.assertIn("remaining_requests", stats)
        self.assertIn("reset_in_human", stats)
        self.assertIn("active_provider", stats)
        self.assertIn("daily_limit", stats)
        self.assertGreaterEqual(stats["daily_limit"], 100)

    def test_quota_tracker_format_message(self):
        """Verify format_usage_message includes markdown formatting and key info."""
        msg = quota_tracker.format_usage_message()
        self.assertIn("AI Chat Usage & Quota Tracker", msg)
        self.assertIn("Remaining Quota", msg)
        self.assertIn("Quota Resets", msg)
        self.assertIn("%", msg)

    def test_api_ai_usage_endpoint(self):
        """Verify /api/ai/usage endpoint responds with 200 and JSON usage data."""
        res = self.client.get("/api/ai/usage")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("percentage_used", data)
        self.assertIn("remaining_requests", data)
        self.assertIn("reset_in_human", data)

    def test_limit_command(self):
        """Verify !limit or !usage command returns quota information."""
        reply, is_fb = gemini_brain.process_query("student_1", "Student", "!limit")
        self.assertFalse(is_fb)
        self.assertIn("AI Chat Usage & Quota Tracker", reply)
        self.assertIn("Remaining Quota", reply)

        reply2, is_fb2 = gemini_brain.process_query("student_2", "Student", "!usage")
        self.assertFalse(is_fb2)
        self.assertIn("AI Chat Usage & Quota Tracker", reply2)

    def test_natural_fallback_handling(self):
        """Verify unknown/out-of-domain queries return the natural polite fallback."""
        from core.gemini_brain import FALLBACK_MESSAGE_BANGLISH
        self.assertIn("Ei bishoy-ta amar jana nei", FALLBACK_MESSAGE_BANGLISH)

if __name__ == "__main__":
    unittest.main()
