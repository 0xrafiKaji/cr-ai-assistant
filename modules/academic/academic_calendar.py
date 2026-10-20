import sqlite3
from datetime import datetime, date
from typing import List, Dict, Any, Optional
from core.database import DB_PATH

class AcademicCalendarManager:
    """Manages SMUCT Revised Academic Calendar (Summer 2026) and custom date overrides."""

    def __init__(self):
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS academic_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            event_type TEXT NOT NULL, -- 'regular', 'prep_leave', 'exam', 'holiday', 'makeup', 'result', 'break'
            start_date TEXT NOT NULL, -- YYYY-MM-DD
            end_date TEXT NOT NULL,   -- YYYY-MM-DD
            classes_suspended BOOLEAN DEFAULT 0,
            description TEXT,
            is_custom BOOLEAN DEFAULT 0
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sheet_configs (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """)
        conn.commit()

        # Seed Summer 2026 calendar if empty
        cursor.execute("SELECT COUNT(*) FROM academic_events WHERE is_custom = 0")
        count = cursor.fetchone()[0]
        if count == 0:
            self._seed_summer_2026_events(cursor)
            conn.commit()

        conn.close()

    def _seed_summer_2026_events(self, cursor):
        events = [
            ("Summer 2026 Classes Start", "regular", "2026-08-22", "2026-10-09", False, "Regular semester classes"),
            ("Eid E-Milad-Un Nabi Holiday", "holiday", "2026-08-26", "2026-08-26", True, "University Holiday (Wednesday)"),
            ("Janmastami Holiday", "holiday", "2026-09-04", "2026-09-04", True, "University Holiday (Friday)"),
            ("Makeup Classes Week (Wed & Fri)", "makeup", "2026-10-10", "2026-10-12", False, "Makeup classes for Wednesday & Friday"),
            ("Question Moderation", "moderation", "2026-10-13", "2026-10-15", False, "Midterm Question Moderation"),
            ("Class Attendance Input Locked", "deadline", "2026-10-14", "2026-10-14", False, "Attendance locked at 12:00 AM"),
            ("Midterm Preparation Leave & Submission", "prep_leave", "2026-10-16", "2026-10-19", True, "Prep leave before Midterm. Regular classes are SUSPENDED."),
            ("Admit Card Issuance", "admit_card", "2026-10-17", "2026-10-17", False, "Admit cards issued by Office of Exam Controller"),
            ("Tuition Fees Payment Deadline", "deadline", "2026-10-19", "2026-10-19", False, "Last date of tuition fee payment for Midterm"),
            ("Durga Puja Holidays", "holiday", "2026-10-20", "2026-10-22", True, "University closed for Durga Puja (Tue, Wed, Thu)"),
            ("Mid-term Examination (Offline Mode)", "exam", "2026-10-23", "2026-11-05", True, "Midterm exams (14 days, Offline mode). No regular classes."),
            ("Overlapped Examination", "exam", "2026-11-06", "2026-11-06", True, "Overlapped examinations"),
            ("National Revolution & Solidarity Day", "holiday", "2026-11-07", "2026-11-07", True, "University Holiday (Saturday)"),
            ("Post-Midterm Regular Classes (Week 08-15)", "regular", "2026-11-08", "2027-01-01", False, "Regular semester classes resume"),
            ("Midterm Result Publication", "result", "2026-11-13", "2026-11-13", False, "Publication of Midterm Exam results"),
            ("Application Deadline for I Grade", "deadline", "2026-11-23", "2026-11-23", False, "Last date for I Grade applications"),
            ("Victory Day Holiday", "holiday", "2026-12-16", "2026-12-16", True, "National Holiday (Wednesday)"),
            ("Christmas Day Holiday", "holiday", "2026-12-25", "2026-12-25", True, "Holiday (Friday)"),
            ("Makeup Classes Week (Sat, Wed, Fri)", "makeup", "2027-01-02", "2027-01-04", False, "Final exam makeup classes"),
            ("Final Exam Question Moderation", "moderation", "2027-01-05", "2027-01-07", False, "Question moderation for finals"),
            ("Final Exam Attendance Locked", "deadline", "2027-01-06", "2027-01-06", False, "Attendance locked at 12:00 AM"),
            ("Final Exam Prep Leave", "prep_leave", "2027-01-08", "2027-01-09", True, "Preparation leave for final exams"),
            ("Final Examination (Offline Mode)", "exam", "2027-01-10", "2027-01-23", True, "Final semester examinations"),
            ("Semester Break Holidays", "break", "2027-02-01", "2027-02-03", True, "Semester break before Winter 2027"),
            ("Winter Semester 2027 Commencement", "regular", "2027-02-05", "2027-02-05", False, "Classes start for Winter 2027")
        ]
        cursor.executemany("""
        INSERT INTO academic_events (title, event_type, start_date, end_date, classes_suspended, description, is_custom)
        VALUES (?, ?, ?, ?, ?, ?, 0)
        """, events)

    def check_date_status(self, target_date: date) -> Dict[str, Any]:
        """Checks if a given date has suspended classes, exam, or holiday."""
        d_str = target_date.strftime("%Y-%m-%d")
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Check custom overrides first, then standard events
        cursor.execute("""
        SELECT title, event_type, classes_suspended, description, start_date, end_date 
        FROM academic_events 
        WHERE ? BETWEEN start_date AND end_date 
        ORDER BY is_custom DESC, id DESC
        """, (d_str,))
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return {
                "has_event": False,
                "classes_suspended": False,
                "event_type": "regular",
                "notice": None
            }

        # Check if any event suspends classes
        suspending_event = next((r for r in rows if r[2]), None)
        active_event = suspending_event or rows[0]

        title, ev_type, suspended, desc, s_date, e_date = active_event
        return {
            "has_event": True,
            "classes_suspended": bool(suspended),
            "event_type": ev_type,
            "title": title,
            "description": desc,
            "start_date": s_date,
            "end_date": e_date
        }

    def get_all_events(self) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, event_type, start_date, end_date, classes_suspended, description, is_custom FROM academic_events ORDER BY start_date ASC")
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "id": r[0], "title": r[1], "event_type": r[2], "start_date": r[3],
                "end_date": r[4], "classes_suspended": bool(r[5]), "description": r[6], "is_custom": bool(r[7])
            }
            for r in rows
        ]

    def add_custom_override(self, title: str, event_type: str, start_date: str, end_date: str, classes_suspended: bool, description: str) -> int:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO academic_events (title, event_type, start_date, end_date, classes_suspended, description, is_custom)
        VALUES (?, ?, ?, ?, ?, ?, 1)
        """, (title, event_type, start_date, end_date, int(classes_suspended), description))
        new_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return new_id

    def delete_custom_override(self, event_id: int) -> bool:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM academic_events WHERE id = ? AND is_custom = 1", (event_id,))
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected > 0

academic_calendar = AcademicCalendarManager()
