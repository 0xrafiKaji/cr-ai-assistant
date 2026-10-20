import unittest
import os
from PIL import Image, ImageDraw
from modules.vision.screenshot_parser import screenshot_parser
from core.gemini_brain import gemini_brain

class TestVisionWorkflow(unittest.TestCase):
    def setUp(self):
        # Create a sample synthetic notice image
        self.test_img_path = "/tmp/test_notice.png"
        img = Image.new("RGB", (500, 150), color=(255, 255, 255))
        d = ImageDraw.Draw(img)
        d.text((20, 20), "SMUCT CSE NOTICE", fill=(0, 0, 0))
        d.text((20, 50), "Class Test 2 on Tuesday at 11:30 AM in Room 1504", fill=(0, 0, 0))
        d.text((20, 80), "Course: CSE 1202 - Tahsin Alam", fill=(0, 0, 0))
        img.save(self.test_img_path)

    def tearDown(self):
        if os.path.exists(self.test_img_path):
            os.remove(self.test_img_path)

    def test_screenshot_to_draft_and_approval(self):
        """Test end-to-end vision OCR, draft generation, and approval broadcast with mocked WhatsApp."""
        from unittest.mock import patch, AsyncMock
        # 1. Parse and draft
        ann_id, draft = screenshot_parser.parse_and_draft_announcement(self.test_img_path)
        self.assertGreater(ann_id, 0)
        self.assertIn("1202", draft)

        # 2. Approve announcement via Admin command in GeminiBrain
        with patch("modules.notifier.whatsapp_client.whatsapp_client.send_group_message", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            reply, is_fb = gemini_brain.process_query(
                sender_id="admin_test",
                sender_name="Admin",
                message=f"!approve {ann_id}",
                is_admin=True
            )
            self.assertFalse(is_fb)
            self.assertIn("APPROVED", reply)

if __name__ == "__main__":
    unittest.main()
