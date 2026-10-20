from pydantic import BaseModel
from typing import Optional, List

class ClassSlot(BaseModel):
    day: str
    time_slot: str
    section: str
    course_code: str
    faculty_initial: Optional[str] = ""
    faculty_name: Optional[str] = ""
    room: Optional[str] = ""

    def formatted_summary(self) -> str:
        fac = f" ({self.faculty_name or self.faculty_initial})" if (self.faculty_name or self.faculty_initial) else ""
        room = f" [Room: {self.room}]" if self.room else ""
        return f"⏰ {self.time_slot} | 📚 {self.course_code}{fac}{room}"

class FacultyMember(BaseModel):
    sl: Optional[str] = ""
    name: str
    initial: str
    designation: Optional[str] = ""
    phone: Optional[str] = ""
    email: Optional[str] = ""

class CRMember(BaseModel):
    batch: str
    section: str
    student_id: str
    name: str

class RoutineChange(BaseModel):
    date: str
    sl: Optional[str] = ""
    issue: str
    course: str
    faculty: str
    previous_day: str
    change_hash: str
