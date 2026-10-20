import unittest
import asyncio
from modules.bridge.messenger_filter import messenger_filter

class TestPhase3MessengerBridge(unittest.TestCase):
    def test_01_filter_casual_chat(self):
        """Casual banter in the CR Messenger group should be ignored."""
        casual_msg = "Kire shobai koi? Ajke bikale ground e football khelbi?"
        res = messenger_filter.filter_and_process(sender_name="CR 1A", message_text=casual_msg)
        self.assertFalse(res.get("is_notice"))
        self.assertIn(res.get("category"), ["chit_chat", "casual_chat"])

    def test_02_filter_one_word(self):
        """One-word acknowledgments should be ignored."""
        res = messenger_filter.filter_and_process(sender_name="CR 3B", message_text="ok")
        self.assertFalse(res.get("is_notice"))

    def test_03_detect_genuine_academic_notice(self):
        """Urgent notice regarding class postponement must be detected and polished into Banglish."""
        urgent_msg = (
            "Urgent notice for all batches: Tomorrow (Sunday), EEE 1201 class of 8:30 AM is postponed "
            "due to departmental seminar. Makeup class will be at 3:00 PM in Room UB-110."
        )
        res = messenger_filter.filter_and_process(
            sender_name="Coordinator FHM",
            message_text=urgent_msg,
            check_duplicate=False
        )
        self.assertTrue(res.get("is_notice"))
        notice = res.get("polished_notice")
        self.assertIsNotNone(notice)
        self.assertIn("1201", notice)
        # Verify no broken Bengali unicode characters in notice
        has_bengali_script = any('\u0980' <= c <= '\u09FF' for c in notice)
        self.assertFalse(has_bengali_script, "Notice should not contain Bengali Unicode script to prevent terminal font glitch.")

if __name__ == "__main__":
    unittest.main()
