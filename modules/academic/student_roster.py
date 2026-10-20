import os
import csv
import sqlite3
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict, Any, Optional
from config.settings import settings

DEFAULT_STUDENT_ROSTER = [
    {"serial_no": 1, "roll_no": "1001", "name": "Student One"},
    {"serial_no": 2, "roll_no": "1002", "name": "Student Two"},
    {"serial_no": 3, "roll_no": "1003", "name": "Student Three"},
    {"serial_no": 4, "roll_no": "1004", "name": "Student Four"},
    {"serial_no": 5, "roll_no": "1005", "name": "Student Five"}
]

class StudentRosterManager:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.path.join(settings.DATA_DIR, "assistant.db")
        self._init_db()
        self._seed_roster_if_empty()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Creates tables for student roster, attendance sessions, and attendance records."""
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS cr_students (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    serial_no INTEGER,
                    roll_no TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS cr_attendance_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    course_code TEXT NOT NULL,
                    session_date TEXT NOT NULL,
                    topic TEXT,
                    total_present INTEGER DEFAULT 0,
                    total_absent INTEGER DEFAULT 0,
                    total_late INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS cr_attendance_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    student_roll TEXT NOT NULL,
                    student_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    notes TEXT,
                    FOREIGN KEY (session_id) REFERENCES cr_attendance_sessions (id) ON DELETE CASCADE
                )
            """)
            conn.commit()

    def _seed_roster_if_empty(self):
        """Populates students table if empty, extracting from attendance sheet docx if available."""
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM cr_students")
            count = c.fetchone()[0]
            if count > 0:
                return

            students_to_insert = []
            docx_path = os.path.join(settings.DATA_DIR, "EEE 1201 - Electrical Circuits Attendance Sheet.docx")
            if os.path.exists(docx_path):
                extracted = self._extract_roster_from_docx(docx_path)
                if extracted:
                    students_to_insert = extracted

            if not students_to_insert:
                students_to_insert = DEFAULT_STUDENT_ROSTER

            for s in students_to_insert:
                c.execute("""
                    INSERT OR IGNORE INTO cr_students (serial_no, roll_no, name, is_active)
                    VALUES (?, ?, ?, 1)
                """, (s.get("serial_no"), s["roll_no"], s["name"]))

            conn.commit()
            print(f"✅ Class Student Roster seeded: {len(students_to_insert)} students registered.")

    def _extract_roster_from_docx(self, docx_path: str) -> List[Dict[str, Any]]:
        """Extracts strictly the student serial, roll, and name from docx table without old attendance marks."""
        try:
            with zipfile.ZipFile(docx_path) as z:
                xml_content = z.read("word/document.xml")
            root = ET.fromstring(xml_content)
            namespaces = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            rows = root.findall(".//w:tr", namespaces)
            
            roster = []
            for i, tr in enumerate(rows):
                cells = tr.findall(".//w:tc", namespaces)
                cell_texts = []
                for tc in cells:
                    texts = [node.text for node in tc.findall(".//w:t", namespaces) if node.text]
                    cell_texts.append("".join(texts).strip())
                
                if i == 0 or len(cell_texts) < 3:
                    continue
                
                sl_str = cell_texts[0]
                roll = cell_texts[1].strip()
                name = cell_texts[2].strip()

                if roll and (roll.isdigit() or len(roll) >= 8) and name:
                    try:
                        sl = int(sl_str)
                    except ValueError:
                        sl = len(roster) + 1
                    roster.append({
                        "serial_no": sl,
                        "roll_no": roll,
                        "name": name
                    })
            return roster
        except Exception as e:
            print(f"Warning: Could not parse docx roster: {e}")
            return []

    def get_students(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """Returns list of students ordered by serial_no."""
        with self._get_connection() as conn:
            c = conn.cursor()
            if active_only:
                c.execute("SELECT id, serial_no, roll_no, name, is_active FROM cr_students WHERE is_active = 1 ORDER BY serial_no ASC, roll_no ASC")
            else:
                c.execute("SELECT id, serial_no, roll_no, name, is_active FROM cr_students ORDER BY serial_no ASC, roll_no ASC")
            rows = c.fetchall()
            return [dict(r) for r in rows]

    def add_student(self, roll_no: str, name: str, serial_no: Optional[int] = None) -> int:
        """Adds a new student to the batch roster."""
        with self._get_connection() as conn:
            c = conn.cursor()
            if serial_no is None:
                c.execute("SELECT MAX(serial_no) FROM cr_students")
                max_sl = c.fetchone()[0] or 0
                serial_no = max_sl + 1
            c.execute("""
                INSERT INTO cr_students (serial_no, roll_no, name, is_active)
                VALUES (?, ?, ?, 1)
            """, (serial_no, roll_no.strip(), name.strip()))
            conn.commit()
            return c.lastrowid

    def submit_attendance_session(
        self,
        course_code: str,
        session_date: str,
        topic: str = "",
        records: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Saves a daily class attendance session with individual student records.
        records: list of dicts: [{"roll_no": "...", "name": "...", "status": "P"|"A"|"L", "notes": ""}]
        """
        records = records or []
        present_count = sum(1 for r in records if r.get("status") == "P")
        absent_count = sum(1 for r in records if r.get("status") == "A")
        late_count = sum(1 for r in records if r.get("status") == "L")

        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO cr_attendance_sessions (course_code, session_date, topic, total_present, total_absent, total_late)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (course_code.strip().upper(), session_date.strip(), topic.strip(), present_count, absent_count, late_count))
            session_id = c.lastrowid

            for r in records:
                c.execute("""
                    INSERT INTO cr_attendance_records (session_id, student_roll, student_name, status, notes)
                    VALUES (?, ?, ?, ?, ?)
                """, (session_id, r.get("roll_no", ""), r.get("name", ""), r.get("status", "P"), r.get("notes", "")))

            conn.commit()

        return {
            "session_id": session_id,
            "course_code": course_code.upper(),
            "session_date": session_date,
            "topic": topic,
            "total_present": present_count,
            "total_absent": absent_count,
            "total_late": late_count,
            "total_students": len(records)
        }

    def list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns recent attendance sessions."""
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT id, course_code, session_date, topic, total_present, total_absent, total_late, created_at
                FROM cr_attendance_sessions
                ORDER BY session_date DESC, id DESC
                LIMIT ?
            """, (limit,))
            rows = c.fetchall()
            return [dict(r) for r in rows]

    def get_session_details(self, session_id: int) -> Optional[Dict[str, Any]]:
        """Returns detailed session header + student records."""
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM cr_attendance_sessions WHERE id = ?", (session_id,))
            session = c.fetchone()
            if not session:
                return None

            c.execute("""
                SELECT r.id, r.student_roll, r.student_name, r.status, r.notes, s.serial_no
                FROM cr_attendance_records r
                LEFT JOIN cr_students s ON r.student_roll = s.roll_no
                WHERE r.session_id = ?
                ORDER BY s.serial_no ASC, r.student_roll ASC
            """, (session_id,))
            records = [dict(rec) for rec in c.fetchall()]

            data = dict(session)
            data["records"] = records
            return data

    def delete_session(self, session_id: int) -> bool:
        """Deletes an attendance session and all corresponding student records."""
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM cr_attendance_records WHERE session_id = ?", (session_id,))
            c.execute("DELETE FROM cr_attendance_sessions WHERE id = ?", (session_id,))
            affected = c.rowcount
            conn.commit()
            return affected > 0

    def format_whatsapp_summary(self, session_id: int) -> str:
        """Formats an aesthetic WhatsApp report of the session for the Notice Group."""
        details = self.get_session_details(session_id)
        if not details:
            return "Attendance session not found."

        total = details["total_present"] + details["total_absent"] + details["total_late"]
        pct = (details["total_present"] / total * 100) if total > 0 else 0

        absent_rolls = [r["student_roll"] for r in details.get("records", []) if r["status"] == "A"]
        absent_str = ", ".join(absent_rolls) if absent_rolls else "None (100% Present!)"

        topic_str = f"\n📝 *Topic:* {details['topic']}" if details.get("topic") else ""

        msg = (
            f"📋 *CLASS ATTENDANCE REPORT*\n"
            f"🏛 *SMUCT CSE {settings.BATCH_NAME} Batch (Section {settings.SECTION_NAME})*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📚 *Course:* {details['course_code']}\n"
            f"📅 *Date:* {details['session_date']}{topic_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ *Present:* {details['total_present']} / {total} ({pct:.1f}%)\n"
            f"❌ *Absent ({len(absent_rolls)}):* {absent_str}\n"
        )
        if details.get("total_late", 0) > 0:
            late_rolls = [r["student_roll"] for r in details.get("records", []) if r["status"] == "L"]
            msg += f"🕒 *Late ({details['total_late']}):* {', '.join(late_rolls)}\n"

        msg += (
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"— Rafi (CR, 38th Batch)"
        )
        return msg

    def export_session_csv(self, session_id: int) -> Optional[str]:
        """Exports a single session's attendance records to CSV."""
        details = self.get_session_details(session_id)
        if not details:
            return None

        os.makedirs(os.path.join(settings.DATA_DIR, "exports"), exist_ok=True)
        fname = f"attendance_{details['course_code']}_{details['session_date'].replace('-', '')}_session{session_id}.csv"
        fpath = os.path.join(settings.DATA_DIR, "exports", fname)

        with open(fpath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Course", details["course_code"]])
            writer.writerow(["Date", details["session_date"]])
            writer.writerow(["Topic", details.get("topic", "")])
            writer.writerow(["Present", details["total_present"], "Absent", details["total_absent"], "Late", details.get("total_late", 0)])
            writer.writerow([])
            writer.writerow(["Serial", "Roll No", "Student Name", "Status", "Notes"])

            for r in details.get("records", []):
                writer.writerow([r.get("serial_no", ""), r["student_roll"], r["student_name"], r["status"], r.get("notes", "")])

        return fpath

    def export_all_sessions_csv(self) -> str:
        """Exports full attendance matrix of all students across all sessions."""
        students = self.get_students(active_only=False)
        sessions = self.list_sessions(limit=200)
        sessions.reverse()

        os.makedirs(os.path.join(settings.DATA_DIR, "exports"), exist_ok=True)
        fpath = os.path.join(settings.DATA_DIR, "exports", "batch_attendance_full_matrix.csv")

        matrix: Dict[str, Dict[int, str]] = {s["roll_no"]: {} for s in students}
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT session_id, student_roll, status FROM cr_attendance_records")
            for sid, roll, status in c.fetchall():
                if roll in matrix:
                    matrix[roll][sid] = status

        with open(fpath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            header = ["Sl", "Roll No", "Student Name"] + [f"{s['course_code']} ({s['session_date']})" for s in sessions]
            writer.writerow(header)

            for s in students:
                row = [s["serial_no"], s["roll_no"], s["name"]]
                for sess in sessions:
                    st = matrix[s["roll_no"]].get(sess["id"], "-")
                    row.append(st)
                writer.writerow(row)

        return fpath

student_roster = StudentRosterManager()
