import sqlite3
import csv
import io
import os
from datetime import datetime
from typing import List, Dict, Optional, Any
from config.settings import settings

DB_PATH = os.path.join(settings.DATA_DIR, "assistant.db")

class ClassHistoryTracker:
    def __init__(self):
        pass

    def log_class(self, course_code: str, faculty_initial: str, status: str = "held", date_str: Optional[str] = None, room: str = "", notes: str = "") -> int:
        """
        Logs a class instance into SQLite.
        status: 'held', 'cancelled', 'makeup'
        """
        if not date_str:
            now = datetime.now()
            date_str = now.strftime("%Y-%m-%d")
            day_of_week = now.strftime("%A")
        else:
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                day_of_week = dt.strftime("%A")
            except Exception:
                day_of_week = datetime.now().strftime("%A")

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO class_history (date_str, day_of_week, course_code, faculty_initial, room_number, status, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (date_str, day_of_week, course_code.upper().strip(), faculty_initial.upper().strip(), room.strip(), status.lower().strip(), notes.strip()))
        log_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return log_id

    def get_history(self, filter_query: Optional[str] = None) -> str:
        """
        Generates an exact summary table with dates, days of the week, faculty, and status.
        """
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        if filter_query:
            q = f"%{filter_query.strip().upper()}%"
            cursor.execute("""
            SELECT date_str, day_of_week, course_code, faculty_initial, room_number, status, notes
            FROM class_history
            WHERE course_code LIKE ? OR faculty_initial LIKE ?
            ORDER BY date_str DESC
            """, (q, q))
        else:
            cursor.execute("""
            SELECT date_str, day_of_week, course_code, faculty_initial, room_number, status, notes
            FROM class_history
            ORDER BY date_str DESC
            LIMIT 30
            """)

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return "ℹ️ No class logs found in the database. Use '!logclass <course> <faculty> <held|cancelled> [notes]' to add."

        total = len(rows)
        held_count = sum(1 for r in rows if r[5] == "held")
        cancelled_count = sum(1 for r in rows if r[5] == "cancelled")
        makeup_count = sum(1 for r in rows if r[5] == "makeup")

        lines = [
            "📊 *CLASS HISTORY LOG REPORT*",
            f"🏛 *SMUCT CSE {settings.BATCH_NAME} Batch (Section {settings.SECTION_NAME})*",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"📈 Total Tracked: {total} | ✔ Held: {held_count} | ❌ Cancelled: {cancelled_count} | 🔄 Makeup: {makeup_count}\n"
        ]

        for r in rows:
            icon = "✔" if r[5] == "held" else ("❌" if r[5] == "cancelled" else "🔄")
            room_info = f" [Room: {r[4]}]" if r[4] else ""
            note_info = f" ({r[6]})" if r[6] else ""
            lines.append(f"• {icon} *{r[0]} ({r[1]})*: {r[2]} | Faculty: {r[3]} | Status: *{r[5].upper()}*{room_info}{note_info}")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("📁 Type '!exportclasses' to download as CSV.")
        return "\n".join(lines)

    def export_csv(self, output_path: Optional[str] = None) -> str:
        """Export all class logs into CSV format."""
        if not output_path:
            output_path = os.path.join(settings.DATA_DIR, "class_history_export.csv")

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT date_str, day_of_week, course_code, faculty_initial, room_number, status, notes FROM class_history ORDER BY date_str ASC")
        rows = cursor.fetchall()
        conn.close()

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "Day of Week", "Course Code", "Faculty Initial", "Room", "Status", "Notes"])
            for r in rows:
                writer.writerow(r)

        return output_path

    def import_csv(self, filepath: str) -> int:
        """Import class logs from a CSV file."""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        count = 0

        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            headers = next(reader, None)
            for row in reader:
                if len(row) >= 6:
                    cursor.execute("""
                    INSERT INTO class_history (date_str, day_of_week, course_code, faculty_initial, room_number, status, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (row[0], row[1], row[2], row[3], row[4], row[5], row[6] if len(row) > 6 else ""))
                    count += 1

        conn.commit()
        conn.close()
        return count

class_tracker = ClassHistoryTracker()
