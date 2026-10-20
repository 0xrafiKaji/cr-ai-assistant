import hashlib
import json
import re
from typing import Dict, Any, Tuple, Optional
from config.settings import settings
from core.database import save_announcement, is_change_announced, record_announced_change
from modules.notifier.whatsapp_client import whatsapp_client

CLASSIFIER_PROMPT = f"""You are the Intelligent Notice Classifier for {settings.ADMIN_NAME}, Class Representative of {settings.UNIVERSITY_NAME} {settings.DEPARTMENT_NAME} {settings.BATCH_NAME} Batch (Section {settings.SECTION_NAME}).

You monitor the Messenger CR Group where department notices, teachers' messages, and CR discussions occur.

TASK:
Examine the incoming message from the Messenger CR Group. Determine if it is a genuine, important academic/administrative notice relevant to students (e.g. class cancellation, make-up class, exam schedule, room shift, university holiday, department program, fee/registration deadline).

Ignore casual chit-chat, memes, personal banter, one-word replies ("ok", "seen", "yes", "done"), questions from students, or non-academic talk.

STRICT FORMATTING RULE:
- The announcement MUST be strictly in Banglish (Bengali written in English letters) or English.
- NEVER use Bengali Unicode script (বাংলা হরফ) because it glitches in Linux terminals.

Respond strictly in valid JSON with this schema:
{{
  "is_notice": true / false,
  "category": "routine_change" | "exam_notice" | "holiday" | "general_notice" | "chit_chat",
  "reason": "Short explanation",
  "polished_notice": "Formatted WhatsApp announcement text with emojis, or null if is_notice is false"
}}
"""

class MessengerNoticeFilter:
    def __init__(self):
        pass

    def filter_and_process(self, sender_name: str, message_text: str, check_duplicate: bool = True) -> Dict[str, Any]:
        """
        Analyzes a message from the Messenger CR group, classifies it,
        and formats an announcement if it's an important notice.
        """
        clean_text = message_text.strip()
        if not clean_text or len(clean_text) < 5:
            return {"is_notice": False, "category": "chit_chat", "reason": "Too short"}

        # Quick heuristic filter for obvious casual messages
        casual_greetings = ["ok", "okk", "seen", "done", "yes", "no", "thik ache", "hmm", "haha", "ki obostha", "kire"]
        if clean_text.lower() in casual_greetings:
            return {"is_notice": False, "category": "chit_chat", "reason": "One-word acknowledgment"}

        # Duplicate check using hash
        msg_hash = hashlib.md5(f"messenger_{clean_text}".encode("utf-8")).hexdigest()
        if check_duplicate and is_change_announced(msg_hash):
            return {"is_notice": False, "category": "duplicate", "reason": "Already broadcasted"}

        from core.gemini_brain import gemini_brain

        prompt = f"""{CLASSIFIER_PROMPT}

INCOMING MESSENGER MESSAGE from "{sender_name}":
\"\"\"{clean_text}\"\"\"

JSON RESULT:"""

        # Call AI Engine (Groq / Gemini)
        raw_response = None
        if gemini_brain.groq_client:
            try:
                resp = gemini_brain.groq_client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": "You are a JSON-only response engine."},
                        {"role": "user", "content": prompt}
                    ],
                    model=settings.GROQ_MODEL,
                    temperature=0.1,
                    response_format={"type": "json_object"}
                )
                raw_response = resp.choices[0].message.content.strip()
            except Exception as e:
                print(f"Groq classification error: {e}")

        if not raw_response:
            raw_response = gemini_brain.generate_content_with_fallback(prompt)

        if not raw_response:
            # Simple keyword fallback if AI is offline
            is_urgent = any(k in clean_text.lower() for k in ["cancel", "makeup", "exam", "ct", "holiday", "room", "chuti", "shift"])
            if is_urgent:
                notice = (
                    f"📢 *NOTICE FROM CR GROUP (Forwarded)*\n"
                    f"🏛 *{settings.UNIVERSITY_NAME} {settings.DEPARTMENT_NAME} {settings.BATCH_NAME} Batch (Section {settings.SECTION_NAME})*\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"👤 *Source:* {sender_name}\n"
                    f"📌 *Message:*\n{clean_text}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"— Forwarded by {settings.ADMIN_NAME}'s CR Assistant Bot"
                )
                return {"is_notice": True, "category": "general_notice", "polished_notice": notice}
            return {"is_notice": False, "category": "chit_chat", "reason": "No notice keywords detected"}

        try:
            # Clean JSON markdown if wrapped in ```json
            cleaned_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_response, flags=re.MULTILINE).strip()
            result = json.loads(cleaned_json)
        except Exception as e:
            print(f"Failed to parse classifier JSON: {e}. Raw: {raw_response}")
            return {"is_notice": False, "category": "parse_error", "reason": str(e)}

        if result.get("is_notice") and result.get("polished_notice"):
            from core.banglish_sanitizer import sanitize_to_banglish
            result["polished_notice"] = sanitize_to_banglish(result["polished_notice"])
            record_announced_change(
                change_hash=msg_hash,
                date_str="",
                issue=result.get("category", "messenger_notice"),
                course=clean_text[:50],
                faculty=sender_name,
                prev_day=""
            )

        return result

    def filter_and_process_image(self, image_bytes: bytes, caption: str = "", sender_name: str = "Coordinator", check_duplicate: bool = True) -> Dict[str, Any]:
        """
        Analyzes an image/photo posted in the Messenger CR group using Gemini Vision,
        determines if it's an official notice/routine/circular, indexes it into RAG,
        and drafts a formatted announcement.
        """
        import io
        import os
        from datetime import datetime
        from PIL import Image

        if not image_bytes or len(image_bytes) < 100:
            return {"is_notice": False, "category": "invalid_image", "reason": "Empty or corrupted image"}

        img_hash = hashlib.md5(image_bytes).hexdigest()
        change_key = f"messenger_img_{img_hash}"

        if check_duplicate and is_change_announced(change_key):
            return {"is_notice": False, "category": "duplicate", "reason": "Already broadcasted"}

        try:
            pil_img = Image.open(io.BytesIO(image_bytes))
        except Exception as e:
            return {"is_notice": False, "category": "invalid_image", "reason": f"Cannot open image: {e}"}

        from core.gemini_brain import gemini_brain
        if not gemini_brain.gemini_client:
            gemini_brain._init_providers()

        prompt = f"""You are the Intelligent Academic Notice & Routine Vision Classifier for {settings.ADMIN_NAME}, Class Representative of {settings.UNIVERSITY_NAME} {settings.DEPARTMENT_NAME} {settings.BATCH_NAME} Batch (Section {settings.SECTION_NAME}).

You monitor the Messenger CR Group where department coordinators, teachers, and CRs post official notices, timetable changes, exam schedules, and circulars as images/photos.

SENDER: {sender_name}
ACCOMPANYING MESSAGE / CAPTION: \"\"\"{caption.strip()}\"\"\"

TASK:
1. Inspect this image and caption carefully.
2. Determine whether it is an official or relevant academic notice, routine update, exam schedule, class cancellation/make-up announcement, faculty circular, room allocation, holiday notice, or university administrative instruction for SMUCT CSE students.
3. If it is NOT an academic notice (e.g. personal selfie, meme, avatar, sticker, or unrelated graphic), return is_notice: false.
4. If it IS an academic notice:
   - Extract all facts: Title, Batch, Section, Course, Date, Time, Room, Faculty, Action items.
   - Draft a polished, formal announcement for the WhatsApp Notice Group.
   - STRICT LANGUAGE RULE: Draft the notice strictly in clean Banglish (Bengali written in English letters) or English.
   - NEVER use Bengali Unicode script (বাংলা হরফ) because it breaks in Linux terminals.

Respond strictly in valid JSON with this schema:
{{
  "is_notice": true / false,
  "category": "routine_change" | "exam_notice" | "holiday" | "general_notice" | "chit_chat",
  "title": "Short title in Banglish/English",
  "reason": "Short explanation",
  "extracted_text": "Extracted text or facts summary",
  "polished_notice": "Formatted WhatsApp announcement with emojis, or null if is_notice is false"
}}
"""

        raw_response = gemini_brain.generate_content_with_fallback([pil_img, prompt])

        if not raw_response:
            return {"is_notice": False, "category": "ai_offline", "reason": "Gemini Vision unavailable"}

        try:
            cleaned_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_response, flags=re.MULTILINE).strip()
            result = json.loads(cleaned_json)
        except Exception as e:
            print(f"Failed to parse vision classifier JSON: {e}. Raw: {raw_response}")
            return {"is_notice": False, "category": "parse_error", "reason": str(e)}

        if result.get("is_notice") and result.get("polished_notice"):
            from core.banglish_sanitizer import sanitize_to_banglish
            result["polished_notice"] = sanitize_to_banglish(result["polished_notice"])
            if result.get("title"):
                result["title"] = sanitize_to_banglish(result["title"])

            # Content-based duplicate check using title & category:
            # Prevents re-broadcasting identical notices even if screenshot image bytes differ slightly
            title_text = (result.get("title") or result.get("extracted_text") or "notice")[:60].strip().lower()
            title_hash = hashlib.md5(f"title_{title_text}".encode("utf-8")).hexdigest()
            if check_duplicate and is_change_announced(title_hash):
                return {"is_notice": False, "category": "duplicate", "reason": f"Already broadcasted notice: '{result.get('title')}'"}

            # 1. Save image to knowledge base storage for persistent RAG memory
            try:
                os.makedirs(settings.KNOWLEDGE_BASE_DIR, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                img_filename = f"messenger_notice_{timestamp}_{img_hash[:8]}.png"
                img_path = os.path.join(settings.KNOWLEDGE_BASE_DIR, img_filename)
                with open(img_path, "wb") as f:
                    f.write(image_bytes)

                # Save companion .meta.json for LocalKnowledgeBase RAG indexing
                meta_path = os.path.join(settings.KNOWLEDGE_BASE_DIR, f"{img_filename}.meta.json")
                meta_content = {
                    "instruction": f"Official notice photo posted by {sender_name} in Messenger CR Group on {datetime.now().strftime('%Y-%m-%d %I:%M %p')}.",
                    "extracted_text": f"Title: {result.get('title')}\nCategory: {result.get('category')}\nFacts:\n{result.get('extracted_text')}\nNotice Draft:\n{result.get('polished_notice')}",
                    "is_active": True,
                    "source": "messenger_image",
                    "timestamp": datetime.now().isoformat()
                }
                with open(meta_path, "w", encoding="utf-8") as mf:
                    json.dump(meta_content, mf, indent=2)

                # Refresh knowledge base active memory
                from modules.rag.knowledge_base import knowledge_base
                knowledge_base.load_all()
            except Exception as err:
                print(f"Warning: Failed to persist notice image to knowledge base: {err}")

            # 2. Record announced change to prevent duplicate broadcasts
            record_announced_change(
                change_hash=change_key,
                date_str=datetime.now().strftime("%Y-%m-%d"),
                issue=result.get("category", "messenger_image_notice"),
                course=result.get("title", "Image Notice")[:50],
                faculty=sender_name,
                prev_day=""
            )
            record_announced_change(
                change_hash=title_hash,
                date_str=datetime.now().strftime("%Y-%m-%d"),
                issue=result.get("category", "messenger_image_notice"),
                course=result.get("title", "Image Notice")[:50],
                faculty=sender_name,
                prev_day=""
            )
        else:
            # Mark ignored images as seen to prevent repeated Gemini calls
            record_announced_change(
                change_hash=change_key,
                date_str=datetime.now().strftime("%Y-%m-%d"),
                issue="ignored_image",
                course="Non-Notice Image",
                faculty=sender_name,
                prev_day=""
            )

        return result

    async def relay_if_notice(self, sender_name: str, message_text: str, auto_broadcast: bool = True) -> Tuple[bool, Optional[str]]:
        """
        Classifies incoming message and, if it's a valid notice, broadcasts or queues it.
        Returns: (was_relayed, notice_text_or_reason)
        """
        res = self.filter_and_process(sender_name, message_text)
        if not res.get("is_notice"):
            return (False, res.get("reason", "Not a notice"))

        notice = res.get("polished_notice")

        from modules.config.group_manager import group_manager
        primary_target = group_manager.get_primary_notice_target()

        if auto_broadcast:
            # Save to DB and broadcast to Primary WhatsApp Notice Group
            save_announcement(
                title=f"Messenger Notice: {res.get('category')}",
                content=notice,
                source="messenger_bridge",
                target_group=primary_target,
                status="broadcasted"
            )
            success = await whatsapp_client.send_group_message(primary_target, notice)
            return (success, notice)
        else:
            # Queue for CR's approval
            ann_id = save_announcement(
                title=f"Messenger Notice: {res.get('category')}",
                content=notice,
                source="messenger_bridge",
                target_group=primary_target,
                status="pending_approval"
            )
            return (True, f"Queued for approval (ID: #{ann_id}). Send '!approve {ann_id}' to post.")

    async def relay_image_if_notice(self, image_bytes: bytes, caption: str = "", sender_name: str = "Coordinator", auto_broadcast: bool = True, check_duplicate: bool = True) -> Tuple[bool, Optional[str]]:
        """
        Classifies incoming image notice and, if valid, broadcasts photo + caption to WhatsApp or queues for approval.
        Returns: (was_relayed, notice_text_or_reason)
        """
        import base64
        from modules.config.group_manager import group_manager
        primary_target = group_manager.get_primary_notice_target()

        res = self.filter_and_process_image(image_bytes, caption, sender_name, check_duplicate=check_duplicate)
        if not res.get("is_notice"):
            return (False, res.get("reason", "Not an academic notice"))

        notice = res.get("polished_notice")

        if auto_broadcast:
            save_announcement(
                title=f"Messenger Photo Notice: {res.get('title', res.get('category'))}",
                content=notice,
                source="messenger_bridge_image",
                target_group=primary_target,
                status="broadcasted"
            )
            b64_str = base64.b64encode(image_bytes).decode('utf-8')
            success = await whatsapp_client.send_group_image(
                primary_target,
                message=notice,
                image_base64=b64_str
            )
            return (success, notice)
        else:
            ann_id = save_announcement(
                title=f"Messenger Photo Notice: {res.get('title', res.get('category'))}",
                content=notice,
                source="messenger_bridge_image",
                target_group=primary_target,
                status="pending_approval"
            )
            return (True, f"Queued for approval (ID: #{ann_id}). Send '!approve {ann_id}' to post.")

messenger_filter = MessengerNoticeFilter()
