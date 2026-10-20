import urllib.request
import csv
import io
import json
import os
import hashlib
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from config.settings import settings
from modules.sheets.models import ClassSlot, FacultyMember, CRMember, RoutineChange
from core.database import is_change_announced, record_announced_change

DAYS_OF_WEEK = ["Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
TIME_SLOTS = [
    "8.30 AM - 9.50 AM",
    "10.00 AM - 11.20 AM",
    "11.30 AM - 12.50 PM",
    "1.00 PM - 2.20 PM",
    "2.30 PM - 3.50 PM",
    "4.00 PM - 5.20 PM"
]

class GoogleSheetsSync:
    def __init__(self):
        self.sheet_id = settings.GOOGLE_SHEET_ID
        self.cache_file = os.path.join(settings.DATA_DIR, "sheet_cache.json")
        self.faculty_map: Dict[str, FacultyMember] = {}
        self.cr_map: Dict[str, CRMember] = {}
        self.routine_slots: List[ClassSlot] = []
        self.last_sync: Optional[datetime] = None

    def _fetch_csv(self, gid: str) -> List[List[str]]:
        url = f"https://docs.google.com/spreadsheets/d/{self.sheet_id}/export?format=csv&gid={gid}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (CR-AI-Assistant)"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8")
            reader = list(csv.reader(io.StringIO(content)))
            return reader

    def sync_all(self, force: bool = False) -> Dict[str, int]:
        """Fetch and parse all required sheets."""
        if not self.sheet_id:
            return {
                "faculty_count": 0,
                "cr_count": 0,
                "routine_slots": 0
            }
        try:
            self._sync_faculty()
            self._sync_crs()
            self._sync_routine()
            self.last_sync = datetime.now()
            self._save_cache()
            return {
                "faculty_count": len(self.faculty_map),
                "cr_count": len(self.cr_map),
                "routine_slots": len(self.routine_slots)
            }
        except Exception as e:
            # Fallback to local cache if offline
            if os.path.exists(self.cache_file):
                self._load_cache()
            raise RuntimeError(f"Failed to sync Google Sheets: {e}")

    def _sync_faculty(self):
        rows = self._fetch_csv(settings.GID_FACULTY)
        # Headers: SL, Name, Initial, Designation, Phone, Email
        for row in rows:
            if len(row) >= 6 and row[2].strip() and row[2].strip() != "Initial":
                initial = row[2].strip().upper()
                fac = FacultyMember(
                    sl=row[0].strip(),
                    name=row[1].strip(),
                    initial=initial,
                    designation=row[3].strip(),
                    phone=row[4].strip(),
                    email=row[5].strip()
                )
                self.faculty_map[initial] = fac

    def _sync_crs(self):
        rows = self._fetch_csv(settings.GID_CRS)
        # Formatted with Batch, Semester/Section, ID, Name
        current_batch = ""
        for row in rows:
            if len(row) >= 6:
                batch_cell = row[2].strip()
                if batch_cell:
                    current_batch = batch_cell
                sec_cell = row[3].strip()
                id_cell = row[4].strip()
                name_cell = row[5].strip()
                if sec_cell and id_cell and id_cell != "ID":
                    cr = CRMember(
                        batch=current_batch,
                        section=sec_cell,
                        student_id=id_cell,
                        name=name_cell
                    )
                    self.cr_map[sec_cell.upper()] = cr

    def _sync_routine(self):
        rows = self._fetch_csv(settings.GID_ROUTINE)
        slots: List[ClassSlot] = []
        current_day = "Saturday"

        for row in rows:
            row_header = " ".join(row[:3]).strip()
            for d in DAYS_OF_WEEK:
                if d in row_header:
                    current_day = d
                    break

            if not row or not row[0].strip():
                continue

            sec_id = row[0].strip()
            # We parse all sections, keeping special focus on Batch/Section (e.g. 2A, 1A, etc.)
            for s_idx, t in enumerate(TIME_SLOTS):
                c_idx = 1 + s_idx * 3
                if c_idx < len(row):
                    cell1 = row[c_idx].strip()
                    cell2 = row[c_idx+1].strip() if c_idx+1 < len(row) else ""
                    cell3 = row[c_idx+2].strip() if c_idx+2 < len(row) else ""

                    course, faculty, room = "", "", ""
                    if "\n" in cell1:
                        parts = [p.strip() for p in cell1.split("\n") if p.strip()]
                        if len(parts) >= 3:
                            course, faculty, room = parts[0], parts[1], parts[2]
                        elif len(parts) == 2:
                            course, faculty = parts[0], parts[1]
                            room = cell2 or cell3
                        elif len(parts) == 1:
                            course = parts[0]
                            faculty = cell2
                            room = cell3
                    else:
                        course = cell1
                        faculty = cell2
                        room = cell3

                    if course or faculty or room:
                        fac_member = self.faculty_map.get(faculty.upper())
                        fac_name = fac_member.name if fac_member else ""
                        slots.append(ClassSlot(
                            day=current_day,
                            time_slot=t,
                            section=sec_id,
                            course_code=course,
                            faculty_initial=faculty,
                            faculty_name=fac_name,
                            room=room
                        ))

        self.routine_slots = slots

    def get_routine_for_day(self, day: str, section: str = "2A") -> List[ClassSlot]:
        """Filter routine for a specific day and section (e.g. 2A - I, 2A - II)."""
        day_normalized = day.strip().capitalize()
        results = []
        for s in self.routine_slots:
            if s.day.lower() == day_normalized.lower():
                # Matches "2A" or "2A - I" or "2A - II"
                if section.upper() in s.section.upper():
                    results.append(s)
        return results

    def format_routine_message(self, day: str, section: str = "2A") -> str:
        """Format an aesthetic WhatsApp notice message for the day's routine."""
        day_cap = day.strip().capitalize()
        slots = self.get_routine_for_day(day_cap, section)

        if day_cap in ["Friday", "Thursday"] and not slots:
            return (
                f"📢 *{settings.UNIVERSITY_NAME} {settings.DEPARTMENT_NAME} {settings.BATCH_NAME} Batch (Sec {settings.SECTION_NAME})*\n"
                f"📅 *Schedule for {day_cap}*\n\n"
                f"🎉 *No classes scheduled!* Enjoy your off-day / prep time. ☕✨\n\n"
                f"— {settings.ADMIN_NAME} (CR Assistant Bot)"
            )

        if not slots:
            return (
                f"📢 *{settings.UNIVERSITY_NAME} {settings.DEPARTMENT_NAME} {settings.BATCH_NAME} Batch (Sec {settings.SECTION_NAME})*\n"
                f"📅 *Schedule for {day_cap}*\n\n"
                f"No scheduled classes found in the master routine for this day.\n\n"
                f"— {settings.ADMIN_NAME} (CR Assistant Bot)"
            )

        # Group by sub-sections (e.g. 2A - I and 2A - II)
        by_sub = {}
        for s in slots:
            by_sub.setdefault(s.section, []).append(s)

        lines = [
            f"📢 *CLASS SCHEDULE NOTICE: {day_cap.upper()}*",
            f"🏛 *{settings.UNIVERSITY_NAME} {settings.DEPARTMENT_NAME} {settings.BATCH_NAME} Batch (Section {settings.SECTION_NAME})*",
            "━━━━━━━━━━━━━━━━━━━━━━"
        ]

        for sec, sec_slots in sorted(by_sub.items()):
            lines.append(f"\n🔹 *Group / Section: {sec}*")
            for slot in sec_slots:
                fac = f" | 👤 {slot.faculty_name} ({slot.faculty_initial})" if slot.faculty_initial else ""
                room = f" | 📍 Room: *{slot.room}*" if slot.room else ""
                lines.append(f"• ⏰ *{slot.time_slot}*: {slot.course_code}{fac}{room}")

        lines.append("\n━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("⚠️ *Please arrive on time. Any sudden faculty makeup classes will be notified separately.*")
        lines.append(f"🤖 *Posted automatically by {settings.ADMIN_NAME}'s CR Assistant Agent*")
        return "\n".join(lines)

    def get_faculty_info(self, query: str) -> Optional[FacultyMember]:
        """Search faculty by initials (e.g. 'MN', 'FI') or partial name."""
        q = query.strip().upper()
        if q in self.faculty_map:
            return self.faculty_map[q]
        for fac in self.faculty_map.values():
            if q.lower() in fac.name.lower():
                return fac
        return None

    def get_cr_info(self, section: str) -> Optional[CRMember]:
        """Search CR details for a section (e.g. '2B', '3A')."""
        return self.cr_map.get(section.strip().upper())

    def check_new_changes(self) -> List[RoutineChange]:
        """Check the 'Changes' tab in Google Sheet and return unannounced modifications."""
        try:
            rows = self._fetch_csv(settings.GID_CHANGES)
        except Exception as e:
            print(f"Error fetching Changes tab: {e}")
            return []

        new_changes = []
        # Columns: Date, Sl. No., Issue, Course, Course Teacher, Previous Day
        for row in rows[2:]:
            if len(row) >= 5 and any(row):
                date_str = row[0].strip()
                sl = row[1].strip() if len(row) > 1 else ""
                issue = row[2].strip() if len(row) > 2 else ""
                course = row[3].strip() if len(row) > 3 else ""
                faculty = row[4].strip() if len(row) > 4 else ""
                prev_day = row[5].strip() if len(row) > 5 else ""

                if not (course or issue):
                    continue

                raw_id = f"{date_str}_{issue}_{course}_{faculty}_{prev_day}"
                c_hash = hashlib.md5(raw_id.encode("utf-8")).hexdigest()

                if not is_change_announced(c_hash):
                    change = RoutineChange(
                        date=date_str,
                        sl=sl,
                        issue=issue,
                        course=course,
                        faculty=faculty,
                        previous_day=prev_day,
                        change_hash=c_hash
                    )
                    new_changes.append(change)
        return new_changes

    def format_changes_announcement(self, changes: List[RoutineChange]) -> str:
        """Format an alert notice when the university changes the routine."""
        if not changes:
            return ""
        lines = [
            "🚨 *CRITICAL ROUTINE UPDATE NOTICE* 🚨",
            f"Department of CSE & CSIT ({settings.UNIVERSITY_NAME})",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "The official department routine has just been updated with the following changes:\n"
        ]
        for c in changes:
            lines.append(f"📌 *Course:* {c.course} (Faculty: {c.faculty})")
            if c.date:
                lines.append(f"   🗓 *Effective Date:* {c.date}")
            if c.issue:
                lines.append(f"   ℹ️ *Issue / Change:* {c.issue}")
            if c.previous_day:
                lines.append(f"   🔄 *Previous Timing:* {c.previous_day}")
            lines.append("")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("🔗 Check Master Google Sheet for live verification.")
        lines.append("🤖 *Instant Alert from Rafi's CR Assistant Agent*")
        return "\n".join(lines)

    def _save_cache(self):
        data = {
            "last_sync": self.last_sync.isoformat() if self.last_sync else "",
            "faculty": {k: v.model_dump() for k, v in self.faculty_map.items()},
            "crs": {k: v.model_dump() for k, v in self.cr_map.items()},
            "routine": [s.model_dump() for s in self.routine_slots]
        }
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load_cache(self):
        if not os.path.exists(self.cache_file):
            return
        with open(self.cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.faculty_map = {k: FacultyMember(**v) for k, v in data.get("faculty", {}).items()}
            self.cr_map = {k: CRMember(**v) for k, v in data.get("crs", {}).items()}
            self.routine_slots = [ClassSlot(**s) for s in data.get("routine", [])]
            if data.get("last_sync"):
                self.last_sync = datetime.fromisoformat(data["last_sync"])

# Global singleton
sheet_sync = GoogleSheetsSync()
