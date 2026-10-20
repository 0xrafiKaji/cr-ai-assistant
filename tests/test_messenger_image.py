import unittest
import io
import uuid
import asyncio
import json
from unittest.mock import patch
from PIL import Image, ImageDraw
from modules.bridge.messenger_filter import messenger_filter

MOCK_AI_RESPONSE = json.dumps({
    "is_notice": True,
    "category": "routine_change",
    "title": "Midterm Make-up Class Notice",
    "reason": "Official class routine announcement",
    "extracted_text": "Midterm Make-up Class on Wednesday 10:00 AM Room 1502 Course CSE 1201",
    "polished_notice": "📢 *NOTICE: Midterm Make-up Class*\n• Course: CSE 1201\n• Day: Wednesday 10:00 AM\n• Room: 1502\n— CR Assistant"
})

class TestMessengerImageRelay(unittest.TestCase):
    def _make_test_image(self, title_suffix: str = "") -> bytes:
        unique_token = uuid.uuid4().hex[:8]
        img = Image.new("RGB", (600, 200), color=(255, 255, 255))
        d = ImageDraw.Draw(img)
        d.text((20, 20), f"UNIVERSITY NOTICE - {title_suffix} ({unique_token})", fill=(0, 0, 0))
        d.text((20, 50), "DEPARTMENT OF CSE - 38TH BATCH (SECTION 2A)", fill=(0, 0, 0))
        d.text((20, 80), "NOTICE: Midterm Make-up Class on Wednesday 10:00 AM", fill=(0, 0, 0))
        d.text((20, 110), "Room: 1502, Course: CSE 1201, Faculty: Dr. Md. Ayub Ali", fill=(0, 0, 0))

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def test_filter_and_process_image_notice(self):
        """Test that Vision identifies academic notice and extracts details in Banglish/English."""
        img_bytes = self._make_test_image("TEST_FILTER")
        with patch("core.gemini_brain.gemini_brain.generate_content_with_fallback", return_value=MOCK_AI_RESPONSE):
            result = messenger_filter.filter_and_process_image(
                image_bytes=img_bytes,
                caption="Notice from coordinator regarding make-up class",
                sender_name="Department Coordinator",
                check_duplicate=False
            )
            self.assertIn("is_notice", result)
            self.assertTrue(result["is_notice"])
            self.assertIsNotNone(result.get("polished_notice"))

            # Verify no Bengali Unicode script to preserve terminal integrity
            polished = result["polished_notice"]
            has_bengali_unicode = any('\u0980' <= c <= '\u09FF' for c in polished)
            self.assertFalse(has_bengali_unicode, "Polished notice must not contain Bengali Unicode script.")

    def test_relay_image_if_notice(self):
        """Test end-to-end async relay of photo notice with mocked WhatsApp client."""
        from unittest.mock import patch, AsyncMock
        img_bytes = self._make_test_image("TEST_RELAY")
        with patch("core.gemini_brain.gemini_brain.generate_content_with_fallback", return_value=MOCK_AI_RESPONSE), \
             patch("modules.notifier.whatsapp_client.whatsapp_client.send_group_image", new_callable=AsyncMock) as mock_send, \
             patch("modules.bridge.messenger_filter.save_announcement") as mock_save, \
             patch("modules.bridge.messenger_filter.record_announced_change") as mock_rec:
            mock_send.return_value = True
            mock_save.return_value = 999
            was_relayed, details = asyncio.run(
                messenger_filter.relay_image_if_notice(
                    image_bytes=img_bytes,
                    caption="Make-up class routine update",
                    sender_name="Coordinator",
                    auto_broadcast=True,
                    check_duplicate=False
                )
            )
            self.assertTrue(was_relayed)
            self.assertIsNotNone(details)
            mock_send.assert_called_once()

if __name__ == "__main__":
    unittest.main()
