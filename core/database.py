import sqlite3
import os
import json
from datetime import datetime
from config.settings import settings

DB_PATH = os.path.join(settings.DATA_DIR, "assistant.db")

def init_db():
    os.makedirs(settings.DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Message Logs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id TEXT,
        sender_name TEXT,
        message_text TEXT,
        reply_text TEXT,
        channel TEXT, -- 'whatsapp_private', 'whatsapp_group', 'cli'
        is_fallback INTEGER DEFAULT 0,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 2. Sheet Changes History (to prevent duplicate alerts)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sheet_changes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        change_hash TEXT UNIQUE,
        date_str TEXT,
        issue_text TEXT,
        course TEXT,
        faculty TEXT,
        previous_day TEXT,
        announced_at DATETIME
    )
    """)

    # 3. Announcements Broadcasted
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS announcements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        content TEXT,
        source TEXT, -- 'routine_6am', 'sheet_change', 'admin_manual', 'messenger_bridge'
        target_group TEXT,
        status TEXT, -- 'pending_approval', 'broadcasted', 'rejected'
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        broadcasted_at DATETIME
    )
    """)

    # 4. Class Tracker / History
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS class_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date_str TEXT,
        day_of_week TEXT,
        course_code TEXT,
        course_name TEXT,
        faculty_initial TEXT,
        room_number TEXT,
        status TEXT, -- 'held', 'cancelled', 'makeup'
        notes TEXT,
        logged_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 5. Assessment Tracker (CT, Quiz, Assignment, Presentation)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS assessments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_code TEXT,
        assessment_type TEXT, -- 'CT', 'Quiz', 'Assignment', 'Presentation'
        number INTEGER DEFAULT 1,
        scheduled_date TEXT,
        status TEXT DEFAULT 'planned', -- 'planned', 'completed'
        notes TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 6. Student Attendance History
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS attendance_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT,
        course_code TEXT,
        total_classes INTEGER DEFAULT 0,
        attended_classes INTEGER DEFAULT 0,
        percentage REAL DEFAULT 100.0,
        last_checked_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 7. Pending Emails Approval Queue
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pending_emails (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipient_email TEXT,
        recipient_name TEXT,
        subject TEXT,
        body TEXT,
        status TEXT DEFAULT 'pending_approval', -- 'pending_approval', 'sent', 'rejected'
        drafted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        sent_at DATETIME
    )
    """)

    # 8. Custom Knowledge Q&As / Direct Answers set by Rafi
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS custom_qa (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        keywords TEXT DEFAULT '',
        category TEXT DEFAULT 'custom',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()

def log_message(sender_id: str, sender_name: str, message: str, reply: str, channel: str = "whatsapp_private", is_fallback: bool = False):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO messages (sender_id, sender_name, message_text, reply_text, channel, is_fallback)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (sender_id, sender_name, message, reply, channel, 1 if is_fallback else 0))
    conn.commit()
    conn.close()

def is_change_announced(change_hash: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM sheet_changes WHERE change_hash = ?", (change_hash,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def record_announced_change(change_hash: str, date_str: str, issue: str, course: str, faculty: str, prev_day: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR IGNORE INTO sheet_changes (change_hash, date_str, issue_text, course, faculty, previous_day, announced_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (change_hash, date_str, issue, course, faculty, prev_day, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def save_announcement(title: str, content: str, source: str, target_group: str, status: str = "broadcasted") -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO announcements (title, content, source, target_group, status, broadcasted_at)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (title, content, source, target_group, status, datetime.now().isoformat() if status == "broadcasted" else None))
    ann_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return ann_id

def add_custom_qa(question: str, answer: str, keywords: str = "", category: str = "custom") -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO custom_qa (question, answer, keywords, category, updated_at)
    VALUES (?, ?, ?, ?, ?)
    """, (question.strip(), answer.strip(), keywords.strip(), category, datetime.now().isoformat()))
    qa_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return qa_id

def get_all_custom_qa():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, question, answer, keywords, category, created_at, updated_at FROM custom_qa ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "question": r[1],
            "answer": r[2],
            "keywords": r[3],
            "category": r[4],
            "created_at": r[5],
            "updated_at": r[6]
        }
        for r in rows
    ]

def delete_custom_qa(qa_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM custom_qa WHERE id = ?", (qa_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def update_custom_qa(qa_id: int, question: str, answer: str, keywords: str = "", category: str = "custom") -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE custom_qa
    SET question = ?, answer = ?, keywords = ?, category = ?, updated_at = ?
    WHERE id = ?
    """, (question.strip(), answer.strip(), keywords.strip(), category, datetime.now().isoformat(), qa_id))
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated

def search_custom_qa(query: str):
    words = [w.strip().lower() for w in query.split() if len(w.strip()) >= 2]
    if not words:
        return []
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, question, answer, keywords, category FROM custom_qa")
    rows = cursor.fetchall()
    conn.close()

    results = []
    q_lower = query.lower()
    for r in rows:
        qa_id, q_text, ans_text, kws, cat = r
        combined = f"{q_text} {ans_text} {kws}".lower()
        score = sum(1 for w in words if w in combined)
        if any(kw.strip().lower() in q_lower for kw in kws.split(",") if kw.strip()):
            score += 3
        if q_lower in q_text.lower() or q_text.lower() in q_lower:
            score += 5
        if score > 0:
            results.append((score, {
                "id": qa_id,
                "question": q_text,
                "answer": ans_text,
                "keywords": kws,
                "category": cat
            }))

    results.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in results[:5]]

init_db()
