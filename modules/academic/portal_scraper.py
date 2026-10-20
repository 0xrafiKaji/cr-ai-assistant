import sqlite3
import os
import asyncio
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple
from playwright.async_api import async_playwright

from config.settings import settings
from core.database import DB_PATH
from modules.notifier.whatsapp_client import whatsapp_client
from modules.mailer.email_service import email_service

ADMIN_EMAIL = getattr(settings, "ADMIN_EMAIL", "") or os.getenv("ADMIN_EMAIL", "")

class StudentPortalScraper:
    def __init__(self):
        self.student_id = settings.ADMIN_STUDENT_ID or os.getenv("ADMIN_STUDENT_ID", "")
        self.portal_url = settings.STUDENT_PORTAL_URL or os.getenv("STUDENT_PORTAL_URL", "https://iems.smuct.ac.bd/Login")
        self.portal_user = settings.STUDENT_PORTAL_USER or os.getenv("STUDENT_PORTAL_USER", "")
        self.portal_pass = settings.STUDENT_PORTAL_PASS or os.getenv("STUDENT_PORTAL_PASS", "")
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            course_code TEXT NOT NULL,
            total_classes INTEGER NOT NULL,
            attended_classes INTEGER NOT NULL,
            absent_classes INTEGER DEFAULT 0,
            percentage REAL NOT NULL,
            last_checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance_absents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            course_code TEXT NOT NULL,
            absent_date TEXT NOT NULL,
            day_name TEXT,
            class_time TEXT,
            faculty_name TEXT,
            notified_email BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(student_id, course_code, absent_date, class_time)
        )
        """)
        conn.commit()
        conn.close()

    async def scrape_portal_attendance(self) -> List[Dict[str, Any]]:
        """
        Logs into SMUCT i-EMS Portal with Rafi's credentials,
        scrapes all 9 registered courses and their real attendance tables.
        """
        if not self.portal_user or not self.portal_pass:
            print("ℹ️ Student portal credentials not configured. Skipping automated scraper.")
            return []

        print("🔐 Logging into Student Portal...")
        results = []
        new_absents_found = []

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                page = await context.new_page()

                # Step 1: Login
                await page.goto(self.portal_url, timeout=35000)
                await page.fill('#UserName', self.portal_user)
                await page.fill('#password-field', self.portal_pass)
                await page.click('button[type="submit"], input[type="submit"]')
                await page.wait_for_timeout(3500)

                # Step 2: Extract course links from Student Dashboard
                courses = await page.eval_on_selector_all('a', '''els => {
                    const list = [];
                    for (let el of els) {
                        if (el.href && el.href.includes('CoursePane?id=') && !el.href.includes('#')) {
                            list.push({ name: el.innerText.trim(), url: el.href });
                        }
                    }
                    return list;
                }''')

                print(f"📚 Found {len(courses)} registered courses on dashboard.")

                # Step 3: Iterate through each course attendance pane
                for c in courses:
                    c_name = c["name"]
                    c_url = c["url"] + "#Attendance"
                    await page.goto(c_url, timeout=30000)
                    await page.wait_for_timeout(1800)

                    # Extract rows from table
                    rows = await page.eval_on_selector_all('#Attendance table tbody tr', '''trs => trs.map(tr => 
                        Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim())
                    ).filter(r => r.length >= 7)''')

                    p_count = sum(1 for r in rows if any('Present' == cell for cell in r))
                    a_count = sum(1 for r in rows if any('Absent' == cell for cell in r))
                    tot = p_count + a_count
                    pct = round((p_count / tot * 100), 1) if tot > 0 else 100.0

                    course_info = {
                        "course_code": c_name,
                        "total_classes": tot,
                        "attended_classes": p_count,
                        "absent_classes": a_count,
                        "percentage": pct,
                        "absents": []
                    }

                    # Check for absents in this course
                    for r in rows:
                        if any('Absent' == cell for cell in r):
                            # r[1]: Date, r[2]: Day, r[3]: Time, r[-1]: Teacher
                            abs_date = r[1] if len(r) > 1 else "Unknown"
                            day_name = r[2] if len(r) > 2 else ""
                            class_time = r[3] if len(r) > 3 else ""
                            teacher = r[-1] if len(r) > 4 else ""

                            course_info["absents"].append({
                                "date": abs_date,
                                "day": day_name,
                                "time": class_time,
                                "teacher": teacher
                            })

                            # Record in DB
                            is_new = self._record_absent(c_name, abs_date, day_name, class_time, teacher)
                            if is_new:
                                new_absents_found.append((c_name, abs_date, day_name, class_time, teacher, pct))

                    self.update_attendance_record(c_name, tot, p_count, a_count, pct)
                    results.append(course_info)

                await browser.close()

            # Step 4: Dispatch Absent Email Alerts to Rafi if any new absent occurred
            if new_absents_found:
                await self._send_absent_email_alerts(new_absents_found)

            return results
        except Exception as e:
            print(f"⚠️ Error scraping student portal: {e}")
            return self.get_latest_attendance()

    def _record_absent(self, course: str, abs_date: str, day: str, time_slot: str, teacher: str) -> bool:
        """Saves absent occurrence to SQLite. Returns True if this is a newly logged absence."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute("""
            INSERT INTO attendance_absents (student_id, course_code, absent_date, day_name, class_time, faculty_name, notified_email)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """, (self.student_id, course, abs_date, day, time_slot, teacher))
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            conn.close()
            return False

    async def _send_absent_email_alerts(self, absents: List[Tuple]):
        """Sends an urgent email notification to admin email when absent is detected."""
        target_email = settings.ADMIN_EMAIL or ADMIN_EMAIL
        if not target_email:
            print("ℹ️ Admin email not configured. Skipping absentee email alerts.")
            return

        print(f"📧 Sending absentee alert email to {target_email}...")
        for c_name, abs_date, day, time_slot, teacher, pct in absents:
            subject = f"⚠️ Attendance Alert: Marked ABSENT in {c_name} ({abs_date})"
            body = (
                f"Respected {settings.ADMIN_NAME},\n\n"
                f"This is an automated alert from your Autonomous AI Assistant Agent.\n\n"
                f"You were marked ABSENT on your official Student Portal:\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📚 Course:       {c_name}\n"
                f"📅 Date & Day:   {abs_date} ({day})\n"
                f"⏰ Class Time:   {time_slot}\n"
                f"👤 Faculty:      {teacher}\n"
                f"📊 Current Rate: {pct}%\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"⚠️ IMPORTANT GUIDANCE:\n"
                f"According to academic regulations, if this absence was due to sickness or valid emergency, "
                f"please submit an application with supporting documents to {teacher} or the Head of Department (HOD) "
                f"to prevent non-collegiate or discollegiate penalties before semester finals.\n\n"
                f"Best regards,\n"
                f"Your Autonomous AI Assistant Agent\n"
                f"{settings.UNIVERSITY_NAME} {settings.DEPARTMENT_NAME} {settings.BATCH_NAME} (Section {settings.SECTION_NAME})"
            )

            # Insert into pending_emails and dispatch
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO pending_emails (recipient_email, recipient_name, subject, body, status)
            VALUES (?, ?, ?, ?, 'pending_approval')
            """, (target_email, settings.ADMIN_NAME, subject, body))
            email_id = cursor.lastrowid
            conn.commit()

            # Mark notified
            cursor.execute("""
            UPDATE attendance_absents SET notified_email = 1 
            WHERE student_id = ? AND course_code = ? AND absent_date = ?
            """, (self.student_id, c_name, abs_date))
            conn.commit()
            conn.close()

            # Attempt live send
            email_service.send_approved_email(email_id)

    def update_attendance_record(self, course_code: str, total_classes: int, attended_classes: int, absent_classes: int, pct: float):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO attendance_records (student_id, course_code, total_classes, attended_classes, absent_classes, percentage, last_checked_at)
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (self.student_id, course_code.strip(), total_classes, attended_classes, absent_classes, pct))
        conn.commit()
        conn.close()

    def get_latest_attendance(self) -> List[Dict[str, Any]]:
        """Fetch latest attendance records per course from DB."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
        SELECT course_code, total_classes, attended_classes, absent_classes, percentage, last_checked_at
        FROM attendance_records
        WHERE student_id = ?
        ORDER BY last_checked_at DESC
        """, (self.student_id,))
        rows = cursor.fetchall()

        seen = {}
        for r in rows:
            code = r[0]
            if code not in seen:
                # Fetch absents for this course
                cursor.execute("""
                SELECT absent_date, day_name, class_time, faculty_name 
                FROM attendance_absents 
                WHERE student_id = ? AND course_code = ?
                ORDER BY absent_date DESC
                """, (self.student_id, code))
                abs_rows = cursor.fetchall()

                seen[code] = {
                    "course_code": r[0],
                    "total_classes": r[1],
                    "attended_classes": r[2],
                    "absent_classes": r[3],
                    "percentage": r[4],
                    "last_checked": r[5],
                    "absents": [
                        {"date": a[0], "day": a[1], "time": a[2], "teacher": a[3]}
                        for a in abs_rows
                    ]
                }
        conn.close()
        return list(seen.values())

    def seed_real_scraped_data(self):
        """Seed the genuine initial portal data scraped from Rafi's portal."""
        data = [
            ("Data Structure [A]", 13, 13, 0, 100.0, []),
            ("Data Structure Sessional [A]", 11, 6, 5, 54.5, [
                ("08/09/2026", "Tuesday", "05:17 PM - 06:07 PM", "Tahsin Alam"),
                ("15/09/2026", "Tuesday", "04:57 PM - 05:47 PM", "Tahsin Alam"),
                ("22/09/2026", "Tuesday", "04:43 PM - 05:33 PM", "Tahsin Alam"),
                ("29/09/2026", "Tuesday", "02:04 PM - 02:54 PM", "Tahsin Alam"),
                ("06/10/2026", "Tuesday", "12:17 PM - 01:07 PM", "Tahsin Alam"),
            ]),
            ("Object Oriented Programming [A]", 14, 11, 3, 78.6, [
                ("27/08/2026", "Thursday", "11:30 AM - 01:00 PM", "Faisal Imran"),
                ("20/09/2026", "Sunday", "10:00 AM - 11:30 AM", "Faisal Imran"),
                ("27/09/2026", "Sunday", "11:22 AM - 11:30 AM", "Faisal Imran"),
            ]),
            ("Object Oriented Programming Sessional [A]", 7, 7, 0, 100.0, []),
            ("English Communication Skills [A]", 7, 7, 0, 100.0, []),
            ("Electrical Circuits [A]", 14, 13, 1, 92.9, [
                ("27/09/2026", "Sunday", "09:50 AM - 10:40 AM", "Md. Naim"),
            ]),
            ("Electrical Circuits Sessional [A]", 7, 7, 0, 100.0, []),
            ("Vector Analysis and Linear Algebra [A]", 15, 14, 1, 93.3, [
                ("27/09/2026", "Sunday", "01:00 PM - 02:30 PM", "Md. Abdullah Bin Masud"),
            ]),
            ("Statistics [A]", 14, 13, 1, 92.9, [
                ("27/09/2026", "Sunday", "02:30 PM - 03:50 PM", "Prof. Dr. Md. Ayub Ali"),
            ])
        ]
        for course, tot, pres, ab, pct, abs_list in data:
            self.update_attendance_record(course, tot, pres, ab, pct)
            for a_date, day, t, fac in abs_list:
                self._record_absent(course, a_date, day, t, fac)

    def seed_sample_attendance(self):
        """Seed sample attendance records for fallback using real portal courses."""
        self.seed_real_scraped_data()

    async def check_and_alert_if_low(self, threshold: float = 75.0) -> Tuple[bool, str]:
        """Check if any course attendance is below threshold and generate alert."""
        records = self.get_latest_attendance()
        low_courses = [r for r in records if r["percentage"] < threshold]
        if not low_courses:
            return False, ""

        lines = [
            "⚠️ *CRITICAL ATTENDANCE ALERT*",
            f"👤 Student: {settings.ADMIN_NAME} ({self.student_id})",
            "━━━━━━━━━━━━━━━━━━━━━━"
        ]
        for c in low_courses:
            lines.append(f"• 📚 *{c['course_code']}*: {c['percentage']:.1f}% ({c['attended_classes']}/{c['total_classes']} classes attended)")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("⚠️ Attendance is below 75%! Discollegiate risk in semester final.")
        alert_msg = "\n".join(lines)
        return True, alert_msg

portal_scraper = StudentPortalScraper()
