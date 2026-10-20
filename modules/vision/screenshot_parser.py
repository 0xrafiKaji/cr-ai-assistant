import io
import os
from PIL import Image
from typing import Tuple, Optional
from config.settings import settings
from core.database import save_announcement, init_db
import sqlite3

PROMPT_TEMPLATE = f"""You are the autonomous AI Class Representative (CR) Assistant Agent for {settings.ADMIN_NAME} (Student ID: {settings.ADMIN_STUDENT_ID}).
Institution: {settings.UNIVERSITY_NAME}
Target Batch: {settings.DEPARTMENT_NAME} {settings.BATCH_NAME} Batch, Section {settings.SECTION_NAME}.

Your task:
1. Examine this screenshot notice / routine / handwritten announcement carefully.
2. Extract all key facts: Event, Date, Time, Room, Subject/Course, Faculty, and any action items.
3. Draft a clean, formal, and aesthetic announcement formatted for WhatsApp Notice Group with relevant emojis, clear bullet points, and proper spacing.
4. STRICT LANGUAGE RULE: Draft the notice strictly in clean Banglish or English. Do NOT output Bengali Unicode script (বাংলা হরফ), to prevent broken characters in Linux terminal.

Output format:
📢 *NOTICE: [TITLE]*
🏛 *{settings.UNIVERSITY_NAME} {settings.DEPARTMENT_NAME} {settings.BATCH_NAME} Batch (Section {settings.SECTION_NAME})*
━━━━━━━━━━━━━━━━━━━━━━
[Body with clear bullet points in Banglish or English]
━━━━━━━━━━━━━━━━━━━━━━
⚠️ [Any warning / deadline / instruction]
— {settings.ADMIN_NAME} (CR, {settings.BATCH_NAME} Batch)
"""

class ScreenshotVisionParser:
    def __init__(self):
        pass

    def parse_and_draft_announcement(self, image_input, custom_instruction: Optional[str] = None) -> Tuple[int, str]:
        """
        Accepts PIL Image or file path or bytes, extracts text, drafts announcement,
        and saves it in SQLite with 'pending_approval' status.
        Returns: (announcement_id, drafted_announcement_text)
        """
        if isinstance(image_input, str):
            img = Image.open(image_input)
        elif isinstance(image_input, (bytes, bytearray)):
            img = Image.open(io.BytesIO(image_input))
        else:
            img = image_input

        from core.gemini_brain import gemini_brain
        if not gemini_brain.gemini_client:
            gemini_brain._init_providers()

        prompt = PROMPT_TEMPLATE
        if custom_instruction and custom_instruction.strip():
            prompt += f"\n\nADDITIONAL INSTRUCTION / FOCUS FROM CR:\n{custom_instruction.strip()}"

        drafted_text = gemini_brain.generate_content_with_fallback([img, prompt])

        if not drafted_text:
            drafted_text = (
                f"📢 *NOTICE: CLASS SCHEDULE UPDATE*\n"
                f"🏛 *{settings.UNIVERSITY_NAME} {settings.DEPARTMENT_NAME} {settings.BATCH_NAME} Batch (Section {settings.SECTION_NAME})*\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "• 📌 *Course:* Class Test / Schedule Update\n"
                "• 🗓 *Day:* Updated day\n"
                "• ⏰ *Time:* Scheduled time\n"
                "• 📍 *Room:* Designated Room\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"— {settings.ADMIN_NAME} (CR, {settings.BATCH_NAME} Batch)"
            )

        from core.banglish_sanitizer import sanitize_to_banglish
        drafted_text = sanitize_to_banglish(drafted_text)

        # Save to SQLite approval queue
        ann_id = save_announcement(
            title="Screenshot Notice Draft",
            content=drafted_text,
            source="vision_screenshot",
            target_group=settings.WHATSAPP_NOTICE_GROUP_ID,
            status="pending_approval"
        )

        return (ann_id, drafted_text)

    def draft_from_text(self, raw_text: str, custom_instruction: Optional[str] = None, auto_queue: bool = True) -> Tuple[int, str]:
        """
        Takes raw notes or rough instructions from CR, transforms them into a structured WhatsApp announcement,
        and optionally queues it in SQLite with 'pending_approval' status.
        Returns: (announcement_id, drafted_announcement_text)
        """
        from core.gemini_brain import gemini_brain
        if not gemini_brain.gemini_client:
            gemini_brain._init_providers()

        prompt = f"""You are the autonomous AI Class Representative (CR) Assistant Agent for {settings.ADMIN_NAME} (Student ID: {settings.ADMIN_STUDENT_ID}).
Institution: {settings.UNIVERSITY_NAME}
Target Batch: {settings.DEPARTMENT_NAME} {settings.BATCH_NAME} Batch, Section {settings.SECTION_NAME}.

TASK:
Take the following rough notes, thoughts, or announcement text from {settings.ADMIN_NAME} and draft a clean, formal, aesthetic WhatsApp announcement formatted for the {settings.DEPARTMENT_NAME} {settings.BATCH_NAME} Batch (Section {settings.SECTION_NAME}) WhatsApp Notice Group.

ADMIN'S RAW NOTES:
\"\"\"{raw_text.strip()}\"\"\"
"""
        if custom_instruction and custom_instruction.strip():
            prompt += f"\nADDITIONAL INSTRUCTION / EMPHASIS:\n{custom_instruction.strip()}\n"

        prompt += f"""
STRICT LANGUAGE & FORMATTING RULES:
1. Language: Strictly write in clean Banglish (Bengali in English alphabet) or English. NEVER output Bengali Unicode script (বাংলা হরফ) to prevent broken characters in Linux terminal.
2. Structure:
📢 *NOTICE: [CATCHY CAPITALIZED TITLE]*
🏛 *{settings.UNIVERSITY_NAME} {settings.DEPARTMENT_NAME} {settings.BATCH_NAME} Batch (Section {settings.SECTION_NAME})*
━━━━━━━━━━━━━━━━━━━━━━
[Warm polite greeting to batchmates, clear explanation of the notice]
• 📌 *Subject / Event:* ...
• 🗓 *Date / Day:* ...
• ⏰ *Time:* ...
• 📍 *Room / Venue:* ...
• 👨‍🏫 *Faculty:* ... (if mentioned or known)
━━━━━━━━━━━━━━━━━━━━━━
⚠️ [Any warning, prep instruction, or deadline]
— {settings.ADMIN_NAME} (CR, {settings.BATCH_NAME} Batch)

Output ONLY the final notice text ready for WhatsApp with no meta-chat or explanations.
"""
        drafted_text = gemini_brain.generate_content_with_fallback(prompt)

        if not drafted_text:
            drafted_text = (
                f"📢 *NOTICE: ACADEMIC UPDATE*\n"
                f"🏛 *{settings.UNIVERSITY_NAME} {settings.DEPARTMENT_NAME} {settings.BATCH_NAME} Batch (Section {settings.SECTION_NAME})*\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{raw_text.strip()}\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"— {settings.ADMIN_NAME} (CR, {settings.BATCH_NAME} Batch)"
            )

        from core.banglish_sanitizer import sanitize_to_banglish
        drafted_text = sanitize_to_banglish(drafted_text)

        ann_id = 0
        if auto_queue:
            ann_id = save_announcement(
                title="Text Notice Draft",
                content=drafted_text,
                source="text_draft",
                target_group=settings.WHATSAPP_NOTICE_GROUP_ID,
                status="pending_approval"
            )

        return (ann_id, drafted_text)

    def approve_and_broadcast(self, announcement_id: int) -> Optional[str]:
        """Mark announcement as approved and return text to broadcast."""
        db_path = os.path.join(settings.DATA_DIR, "assistant.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT content FROM announcements WHERE id = ? AND status = 'pending_approval'", (announcement_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None

        content = row[0]
        cursor.execute("UPDATE announcements SET status = 'broadcasted', broadcasted_at = CURRENT_TIMESTAMP WHERE id = ?", (announcement_id,))
        conn.commit()
        conn.close()
        return content

    def reject_announcement(self, announcement_id: int) -> bool:
        """Reject and discard pending announcement."""
        db_path = os.path.join(settings.DATA_DIR, "assistant.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE announcements SET status = 'rejected' WHERE id = ? AND status = 'pending_approval'", (announcement_id,))
        rows = cursor.rowcount
        conn.commit()
        conn.close()
        return rows > 0

screenshot_parser = ScreenshotVisionParser()
