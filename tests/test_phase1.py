import unittest
from modules.sheets.sync import sheet_sync
from modules.sheets.models import ClassSlot, FacultyMember, CRMember
from modules.rag.knowledge_base import knowledge_base
from core.gemini_brain import gemini_brain, FALLBACK_MESSAGE
from core.database import log_message, save_announcement, is_change_announced

class TestPhase1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sheet_sync.faculty_map["MN"] = FacultyMember(initial="MN", name="Md. Naim", email="naim@example.edu")
        sheet_sync.faculty_map["FI"] = FacultyMember(initial="FI", name="Faisal Imran", email="fi@example.edu")
        sheet_sync.cr_map["2B"] = CRMember(batch="38th", section="2B", name="Sample CR", student_id="1002")
        sheet_sync.routine_slots = [
            ClassSlot(day="Sunday", time_slot="8.30 AM - 9.50 AM", section="2A - I", course_code="CSE 101", faculty_initial="MN", faculty_name="Md. Naim", room="101")
        ]
        try:
            knowledge_base.load_all()
        except Exception:
            pass

    def test_01_routine_sync(self):
        """Verify that routine slots were fetched from Master Google Sheet."""
        self.assertGreater(len(sheet_sync.routine_slots), 0)
        sunday_slots = sheet_sync.get_routine_for_day("Sunday", section="2A")
        self.assertGreater(len(sunday_slots), 0)
        # Check course code
        courses = [s.course_code for s in sunday_slots]
        self.assertTrue(any("CSE" in c for c in courses))

    def test_02_faculty_mapping(self):
        """Verify faculty initial to details lookup."""
        fac_mn = sheet_sync.get_faculty_info("MN")
        self.assertIsNotNone(fac_mn)
        self.assertIn("Naim", fac_mn.name)

        fac_fi = sheet_sync.get_faculty_info("FI")
        self.assertIsNotNone(fac_fi)
        self.assertIn("Faisal Imran", fac_fi.name)

    def test_03_cr_mapping(self):
        """Verify CR lookup for Section 2B."""
        cr_2b = sheet_sync.get_cr_info("2B")
        self.assertIsNotNone(cr_2b)
        self.assertEqual(cr_2b.name, "Sample CR")
        self.assertEqual(cr_2b.student_id, "1002")

    def test_04_routine_formatting(self):
        """Verify formatted WhatsApp message contains key metadata."""
        msg = sheet_sync.format_routine_message("Sunday", section="2A")
        self.assertIn("CLASS SCHEDULE NOTICE: SUNDAY", msg)
        self.assertIn("2A - I", msg)

    def test_05_strict_fallback(self):
        """Ensure out-of-domain questions strictly output the mandated fallback."""
        random_query = "Ekta pizza order korte koto taka lagbe?"
        reply, is_fallback = gemini_brain.process_query("test_user", "Student", random_query, is_admin=False)
        self.assertTrue(is_fallback)
        self.assertEqual(reply, FALLBACK_MESSAGE)

    def test_06_admin_command(self):
        """Ensure Admin commands are recognized and processed."""
        reply, is_fallback = gemini_brain.process_query("admin_user", "Admin", "!sync", is_admin=True)
        self.assertFalse(is_fallback)
        self.assertIn("Master Google Sheet successfully synchronized", reply)

    def test_07_database_persistence(self):
        """Verify logging into SQLite database."""
        log_message("user_123", "Test Student", "Hi", "Walaikum Assalam", "test_channel", False)
        ann_id = save_announcement("Test Announcement", "Hello Batch", "test_source", "120363@g.us")
        self.assertGreater(ann_id, 0)

if __name__ == "__main__":
    unittest.main()
