import sqlite3
import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from config.settings import settings

DB_PATH = os.path.join(settings.DATA_DIR, "assistant.db")

DEFAULT_COURSES = [
    {"code": "EEE 1201", "name": "Electrical Circuits", "faculty": "MN", "required_cts": 3, "required_assignments": 2},
    {"code": "CSE 1203", "name": "Data Structures", "faculty": "FI", "required_cts": 3, "required_assignments": 2},
    {"code": "MAT 1203", "name": "Mathematics III", "faculty": "ABM", "required_cts": 3, "required_assignments": 1},
    {"code": "STA 1201", "name": "Statistics", "faculty": "DMAA", "required_cts": 3, "required_assignments": 1},
    {"code": "CSE 1201", "name": "Discrete Math & OOP", "faculty": "TA", "required_cts": 3, "required_assignments": 2},
    {"code": "ECS 1203", "name": "Economics", "faculty": "BAD", "required_cts": 2, "required_assignments": 1}
]

class AssessmentPlanner:
    def __init__(self):
        pass

    def log_assessment(self, course_code: str, assessment_type: str = "CT", number: int = 1, status: str = "completed", scheduled_date: Optional[str] = None, notes: str = "") -> int:
        """Log a completed or planned CT / Quiz / Assignment."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO assessments (course_code, assessment_type, number, scheduled_date, status, notes)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (course_code.upper().strip(), assessment_type.upper().strip(), number, scheduled_date, status.lower().strip(), notes.strip()))
        ass_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return ass_id

    def get_assessment_summary(self) -> str:
        """Get summary of completed vs pending assessments across courses."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT course_code, assessment_type, number, scheduled_date, status, notes FROM assessments ORDER BY course_code, number")
        records = cursor.fetchall()
        conn.close()

        course_map: Dict[str, List[Dict[str, Any]]] = {}
        for r in records:
            course_map.setdefault(r[0], []).append({
                "type": r[1],
                "number": r[2],
                "date": r[3],
                "status": r[4],
                "notes": r[5]
            })

        lines = [
            "📝 *SEMESTER ASSESSMENT STATUS (CTs & Quizzes)*",
            f"🏛 *SMUCT CSE {settings.BATCH_NAME} Batch (Section {settings.SECTION_NAME})*",
            "━━━━━━━━━━━━━━━━━━━━━━\n"
        ]

        for c in DEFAULT_COURSES:
            code = c["code"]
            logged = course_map.get(code, [])
            completed_cts = [item for item in logged if item["type"] == "CT" and item["status"] == "completed"]
            planned_cts = [item for item in logged if item["type"] == "CT" and item["status"] == "planned"]

            status_str = f"Completed CTs: *{len(completed_cts)}/{c['required_cts']}*"
            lines.append(f"📌 *{code}* (Faculty: {c['faculty']}) — {status_str}")

            if completed_cts:
                ct_nums = ", ".join(f"CT-{item['number']}" for item in completed_cts)
                lines.append(f"   ✔ Completed: {ct_nums}")
            if planned_cts:
                pl_info = ", ".join(f"CT-{item['number']} ({item['date'] or 'Date TBD'})" for item in planned_cts)
                lines.append(f"   🗓 Scheduled: {pl_info}")
            if len(completed_cts) + len(planned_cts) < c["required_cts"]:
                remaining = c["required_cts"] - (len(completed_cts) + len(planned_cts))
                lines.append(f"   ⚠️ *{remaining} CT(s) still need to be scheduled!*")
            lines.append("")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("💡 Type '!planassessments' to auto-generate a balanced schedule for remaining CTs.")
        return "\n".join(lines)

    def generate_balanced_plan(self, remaining_weeks: int = 6) -> str:
        """
        Uses AI to generate a workload-balanced draft timetable preventing end-of-semester clumping.
        """
        summary_text = self.get_assessment_summary()

        from core.gemini_brain import gemini_brain

        prompt = f"""You are the Academic Workload Strategist for Rafi, CR of SMUCT CSE 38th Batch (Section 2A).

CURRENT COMPLETED & PENDING ASSESSMENTS:
{summary_text}

TASK:
Analyze the courses with pending CTs, assignments, and quizzes.
Distribute the remaining CTs across the next {remaining_weeks} weeks of the semester.

CRITICAL RULES:
1. MAX 2 CTs per week. NEVER schedule 3 CTs in the same week to prevent student burnout.
2. Group related subjects with at least 2 days gap.
3. Schedule theoretical heavy courses (like CSE 1203 Data Structures, EEE 1201 Circuits) earlier so students have time to revise.
4. Output STRICTLY in clean Banglish or English with emojis and weekly bullet points.
5. Do NOT output Bengali Unicode characters (বাংলা হরফ) to prevent terminal font glitch.
"""

        plan = None
        if gemini_brain.groq_client:
            try:
                resp = gemini_brain.groq_client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model=settings.GROQ_MODEL,
                    temperature=0.2,
                    max_tokens=800
                )
                plan = resp.choices[0].message.content.strip()
            except Exception as e:
                print(f"Groq planner error: {e}")

        if not plan:
            plan = gemini_brain.generate_content_with_fallback(prompt)

        if not plan:
            plan = (
                f"🗓 *DRAFT BALANCED ASSESSMENT PLAN (Next {remaining_weeks} Weeks)*\n\n"
                f"• *Week 1:* EEE 1201 CT-2 + STA 1201 Assignment 1\n"
                f"• *Week 2:* CSE 1203 CT-2 + MAT 1203 CT-2\n"
                f"• *Week 3:* CSE 1201 CT-2 + ECS 1203 Assignment\n"
                f"• *Week 4:* EEE 1201 CT-3 + MAT 1203 CT-3\n"
                f"• *Week 5:* CSE 1203 CT-3 + CSE 1201 CT-3 (Final CTs)\n"
                f"• *Week 6:* Review, Make-up CTs, and Final Project Submissions.\n\n"
                f"— Balanced schedule generated by Rafi's CR Assistant Bot."
            )

        from core.banglish_sanitizer import sanitize_to_banglish
        clean_plan = sanitize_to_banglish(plan)
        self.save_plan(clean_plan)
        return clean_plan

    def save_plan(self, plan_text: str):
        """Save the assessment plan to disk for persistence."""
        plan_path = os.path.join(settings.DATA_DIR, "assessment_plan.txt")
        with open(plan_path, "w", encoding="utf-8") as f:
            f.write(plan_text.strip())

    def get_saved_plan(self) -> str:
        """Get the saved assessment plan."""
        plan_path = os.path.join(settings.DATA_DIR, "assessment_plan.txt")
        if os.path.exists(plan_path):
            with open(plan_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return content
        return (
            f"🗓 *SEMESTER ASSESSMENT & CT SCHEDULE*\n"
            f"🏛 *SMUCT CSE {settings.BATCH_NAME} Batch (Section {settings.SECTION_NAME})*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• Week 1: EEE 1201 CT-2 + STA 1201 Assignment 1\n"
            f"• Week 2: CSE 1203 CT-2 + MAT 1203 CT-2\n"
            f"• Week 3: CSE 1201 CT-2 + ECS 1203 Assignment\n"
            f"• Week 4: EEE 1201 CT-3 + MAT 1203 CT-3\n"
            f"• Week 5: CSE 1203 CT-3 + CSE 1201 CT-3 (Final CTs)\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"— Rafi's CR Assistant"
        )

    def list_assessments(self) -> List[Dict[str, Any]]:
        """List all assessments from SQLite."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, course_code, assessment_type, number, scheduled_date, status, notes FROM assessments ORDER BY course_code, number")
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "id": r[0],
                "course_code": r[1],
                "assessment_type": r[2],
                "number": r[3],
                "scheduled_date": r[4] or "",
                "status": r[5],
                "notes": r[6] or ""
            }
            for r in rows
        ]

    def delete_assessment(self, ass_id: int) -> bool:
        """Delete an assessment record."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM assessments WHERE id = ?", (ass_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

assessment_planner = AssessmentPlanner()
