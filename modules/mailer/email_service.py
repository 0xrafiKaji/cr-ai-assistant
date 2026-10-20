import sqlite3
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Tuple, Optional
from config.settings import settings
from modules.sheets.sync import sheet_sync
from core.database import DB_PATH

EMAIL_SYSTEM_PROMPT = f"""You are the formal academic correspondence secretary for {settings.ADMIN_NAME} (Student ID: {settings.ADMIN_STUDENT_ID}).
{settings.ADMIN_NAME} is the Class Representative (CR) of {settings.DEPARTMENT_NAME} {settings.BATCH_NAME} Batch, Section {settings.SECTION_NAME} at {settings.UNIVERSITY_NAME}.

TASK:
Write an exceptionally polite, formal, and respectful academic email to a university teacher or counterpart CR.

EMAIL STRUCTURE:
Subject: [Clear, specific subject line]

Respected Sir / Dear Colleague,

[Formal opening stating {settings.ADMIN_NAME}'s identity as CR of {settings.BATCH_NAME} Batch, Sec {settings.SECTION_NAME}]
[Clear, polite body paragraph explaining the context / request / proposed date]
[Humble closing stating that the batch awaits guidance]

Sincerely,
{settings.ADMIN_NAME}
Class Representative, {settings.DEPARTMENT_NAME} {settings.BATCH_NAME} Batch (Section {settings.SECTION_NAME})
Student ID: {settings.ADMIN_STUDENT_ID}
{settings.UNIVERSITY_NAME}
"""

class EmailService:
    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", 587))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_pass = os.getenv("SMTP_PASS", "")

    @property
    def current_smtp_user(self) -> str:
        return os.getenv("SMTP_USER", "").strip() or self.smtp_user

    @property
    def current_smtp_pass(self) -> str:
        return os.getenv("SMTP_PASS", "").strip() or self.smtp_pass

    def resolve_recipient(self, query: str) -> Tuple[Optional[str], Optional[str]]:
        """Resolves teacher or CR email from Master Google Sheet."""
        q = query.strip()

        # Check faculty by initial or name
        fac = sheet_sync.get_faculty_info(q)
        if fac and fac.email:
            return (fac.email, fac.name)

        # Check for HOD / Coordinator keywords
        if "hod" in q.lower() or "head" in q.lower():
            fac_hod = sheet_sync.get_faculty_info("FI")
            if fac_hod:
                return (fac_hod.email, fac_hod.name)

        if "coordinator" in q.lower():
            fac_coord = sheet_sync.get_faculty_info("FHM")
            if fac_coord:
                return (fac_coord.email, fac_coord.name)

        # Check CR Section B
        if "2b" in q.lower() or "dip" in q.lower():
            cr_2b = sheet_sync.get_cr_info("2B")
            if cr_2b:
                return (f"{cr_2b.name} (CR Sec 2B)", cr_2b.name)

        return (None, None)

    def draft_email_structured(
        self,
        recipient_query: str,
        topic: str,
        extra_details: str = "",
        recipient_name: Optional[str] = None,
        recipient_email: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Drafts a formal academic email with structured output for interactive UI editing.
        """
        rec_name = recipient_name
        rec_email = recipient_email

        if not rec_email or not rec_name:
            resolved_email, resolved_name = self.resolve_recipient(recipient_query)
            if resolved_email:
                rec_email = rec_email or resolved_email
                rec_name = rec_name or resolved_name
            else:
                rec_email = rec_email or recipient_query
                rec_name = rec_name or recipient_query

        from core.gemini_brain import gemini_brain

        prompt = f"""{EMAIL_SYSTEM_PROMPT}

RECIPIENT: {rec_name} ({rec_email})
TOPIC / OBJECTIVE: {topic}
CONTEXT / MAIN STORY (Apnar Nijer Bhashay): {extra_details}

INSTRUCTIONS:
1. Translate Rafi's casual context/points into polite, eloquent university-standard academic English.
2. Maintain standard university etiquette: polite greeting, clear request with context, humble CR closing.
3. First line MUST be: Subject: [Formal Subject Line]
4. Followed by: Respected Sir / Dear Faculty, and the rest of the body.

Generate the complete email now."""

        draft_content = None
        if gemini_brain.groq_client:
            try:
                resp = gemini_brain.groq_client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model=settings.GROQ_MODEL,
                    temperature=0.2,
                    max_tokens=650
                )
                draft_content = resp.choices[0].message.content.strip()
            except Exception as e:
                print(f"Groq email draft error: {e}")

        if not draft_content and gemini_brain.gemini_client:
            try:
                resp = gemini_brain.gemini_client.models.generate_content(
                    model=settings.GEMINI_MODEL,
                    contents=prompt
                )
                draft_content = resp.text.strip()
            except Exception as e:
                print(f"Gemini email draft error: {e}")

        if not draft_content:
            draft_content = (
                f"Subject: Formal Request Regarding {topic} - {settings.BATCH_NAME} Batch (Sec {settings.SECTION_NAME})\n\n"
                f"Respected Sir,\n\n"
                f"I hope this email finds you in good health. I am {settings.ADMIN_NAME}, Class Representative (CR) of {settings.DEPARTMENT_NAME} {settings.BATCH_NAME} Batch (Section {settings.SECTION_NAME}) at {settings.UNIVERSITY_NAME}.\n\n"
                f"On behalf of all students of our section, I am writing to respectfully bring to your attention the matter regarding {topic}.\n\n"
                f"{extra_details}\n\n"
                f"We would be deeply grateful if you could kindly consider our request and advise us on the next steps at your earliest convenience.\n\n"
                f"Thank you very much for your time and continuous guidance.\n\n"
                f"Sincerely,\n"
                f"{settings.ADMIN_NAME}\n"
                f"Class Representative, {settings.BATCH_NAME} Batch (Section {settings.SECTION_NAME})\n"
                f"Student ID: {settings.ADMIN_STUDENT_ID} | Department of {settings.DEPARTMENT_NAME}\n"
                f"{settings.UNIVERSITY_NAME}"
            )

        # Extract Subject line if present
        subject = f"Academic Request Regarding {topic}"
        body = draft_content
        if "Subject:" in draft_content:
            parts = draft_content.split("\n", 1)
            subject = parts[0].replace("Subject:", "").strip()
            body = parts[1].strip() if len(parts) > 1 else ""

        # Clean any markdown bolding in subject
        subject = subject.replace("**", "").replace("*", "").strip()

        # Save to SQLite pending_emails table
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO pending_emails (recipient_email, recipient_name, subject, body, status)
        VALUES (?, ?, ?, ?, 'pending_approval')
        """, (rec_email, rec_name or rec_email, subject, body))
        email_id = cursor.lastrowid
        conn.commit()
        conn.close()

        preview = (
            f"📧 *DRAFT EMAIL #{email_id} READY FOR APPROVAL*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 *To:* {rec_name} ({rec_email})\n"
            f"📌 *Subject:* {subject}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{body}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ *STRICT HITL RULE:* Email will NOT be sent without confirmation.\n"
            f"👉 Reply with *!sendmail {email_id}* to send, or *!cancelmail {email_id}* to discard."
        )

        return {
            "email_id": email_id,
            "recipient_email": rec_email,
            "recipient_name": rec_name,
            "subject": subject,
            "body": body,
            "preview": preview,
            "status": "pending_approval"
        }

    def draft_email(self, recipient_query: str, topic: str, extra_details: str = "") -> Tuple[int, str]:
        """Backwards-compatible tuple return for CLI / Chat."""
        res = self.draft_email_structured(recipient_query, topic, extra_details)
        return (res["email_id"], res["preview"])

    def update_draft_email(self, email_id: int, recipient_email: Optional[str] = None, recipient_name: Optional[str] = None, subject: Optional[str] = None, body: Optional[str] = None) -> bool:
        """Allows Rafi to edit and refine the drafted email before sending."""
        existing = self.get_email_by_id(email_id)
        if not existing:
            return False

        rec_email = recipient_email.strip() if (recipient_email is not None and recipient_email.strip()) else existing.get("recipient_email", "")
        rec_name = recipient_name.strip() if (recipient_name is not None and recipient_name.strip()) else existing.get("recipient_name", "")
        subj = subject.strip() if (subject is not None and subject.strip()) else existing.get("subject", "")
        bdy = body.strip() if (body is not None and body.strip()) else existing.get("body", "")

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE pending_emails
            SET recipient_email = ?, recipient_name = ?, subject = ?, body = ?
            WHERE id = ? AND status = 'pending_approval'
        """, (rec_email, rec_name, subj, bdy, email_id))
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected > 0

    def get_email_by_id(self, email_id: int) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pending_emails WHERE id = ?", (email_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_recent_emails(self, limit: int = 15) -> list:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pending_emails ORDER BY id DESC LIMIT ?", (limit,))
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    def send_approved_email(self, email_id: int) -> Tuple[bool, str]:
        """Sends an approved email after Rafi explicitly confirms."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT recipient_email, recipient_name, subject, body, status FROM pending_emails WHERE id = ?", (email_id,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            return (False, f"⚠️ Email #{email_id} not found in pending queue.")

        rec_email, rec_name, subject, body, status = row

        if status != "pending_approval":
            conn.close()
            return (False, f"⚠️ Email #{email_id} is already '{status}'.")

        smtp_user = self.current_smtp_user
        smtp_pass = self.current_smtp_pass

        # Send via SMTP if credentials configured, otherwise mock/simulation
        if smtp_user and smtp_pass:
            try:
                msg = MIMEMultipart()
                msg["From"] = f"{settings.ADMIN_NAME} (CR {settings.SECTION_NAME}) <{smtp_user}>"
                msg["To"] = rec_email
                msg["Subject"] = subject
                msg.attach(MIMEText(body, "plain", "utf-8"))

                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15)
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
                server.quit()
                delivery_note = f"Dispatched live via SMTP ({smtp_user}) to {rec_email}"
            except Exception as e:
                conn.close()
                return (False, f"Failed to send email via SMTP: {e}")
        else:
            delivery_note = f"[Simulation Mode] Logged as sent. (To send live via Gmail, add SMTP_USER and SMTP_PASS in .env or Settings modal)"

        cursor.execute("UPDATE pending_emails SET status = 'sent', sent_at = CURRENT_TIMESTAMP WHERE id = ?", (email_id,))
        conn.commit()
        conn.close()
        return (True, f"✅ Email #{email_id} has been SENT successfully!\n• Recipient: {rec_name} ({rec_email})\n• {delivery_note}")

    def send_direct_email(self, to_email: str, subject: str, body: str) -> Tuple[bool, str]:
        """Dispatches an email directly to a specified address and logs it in SQLite."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO pending_emails (recipient_email, recipient_name, subject, body, status)
        VALUES (?, ?, ?, ?, 'sent')
        """, (to_email, settings.ADMIN_NAME, subject, body))
        email_id = cursor.lastrowid
        conn.commit()
        conn.close()

        smtp_user = self.current_smtp_user
        smtp_pass = self.current_smtp_pass

        if smtp_user and smtp_pass:
            try:
                msg = MIMEMultipart()
                msg["From"] = f"{settings.ADMIN_NAME} (CR {settings.SECTION_NAME}) <{smtp_user}>"
                msg["To"] = to_email
                msg["Subject"] = subject
                msg.attach(MIMEText(body, "plain", "utf-8"))

                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15)
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
                server.quit()
                return (True, f"Email successfully dispatched to {to_email} via SMTP.")
            except Exception as e:
                return (False, f"SMTP dispatch failed: {e}")
        else:
            return (True, f"Email logged in simulation mode to {to_email}.")

    def cancel_email(self, email_id: int) -> bool:
        """Cancel and reject a drafted email."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE pending_emails SET status = 'rejected' WHERE id = ? AND status = 'pending_approval'", (email_id,))
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected > 0

email_service = EmailService()
