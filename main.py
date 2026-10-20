import os
import hashlib
import hmac
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Form, UploadFile, File, Request, Response, Depends
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from config.settings import settings
from modules.sheets.sync import sheet_sync
from modules.rag.knowledge_base import knowledge_base
from core.gemini_brain import gemini_brain
from modules.scheduler.routine_jobs import start_scheduler
from modules.notifier.whatsapp_client import whatsapp_client
from core.database import save_announcement

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print(f"🚀 Initializing {settings.ADMIN_NAME}'s AI Assistant Agent Core...")
    try:
        sync_stats = sheet_sync.sync_all()
        print(f"✅ Google Sheets Synced: {sync_stats}")
    except Exception as e:
        print(f"⚠️ Initial sheet sync warning (using cache if available): {e}")

    # Load Knowledge Base
    knowledge_base.load_all()
    print(f"📚 Knowledge Base loaded: {len(knowledge_base.documents)} documents ready.")

    # Start Background Scheduler (6 AM routine + Sheet Change poller)
    start_scheduler()
    print("⏰ Background scheduler started.")

    yield
    print(f"🛑 Shutting down {settings.ADMIN_NAME}'s AI Assistant Agent Core.")

from fastapi.staticfiles import StaticFiles

app = FastAPI(
    title=f"{settings.ADMIN_NAME}'s Autonomous AI CR Assistant Agent",
    description=f"Backend Core for {settings.ADMIN_NAME} (CR, {settings.BATCH_NAME} Batch, Section {settings.SECTION_NAME}, {settings.UNIVERSITY_NAME})",
    version="1.0.0",
    lifespan=lifespan
)

# Mount static files for PWA icons and assets
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/manifest.json")
def get_manifest():
    manifest_path = os.path.join(os.path.dirname(__file__), "static", "manifest.json")
    if os.path.exists(manifest_path):
        return FileResponse(manifest_path, media_type="application/manifest+json")
    raise HTTPException(status_code=404, detail="Manifest not found")

@app.get("/sw.js")
def get_service_worker():
    sw_path = os.path.join(os.path.dirname(__file__), "static", "sw.js")
    if os.path.exists(sw_path):
        return FileResponse(
            sw_path,
            media_type="application/javascript",
            headers={"Service-Worker-Allowed": "/"}
        )
    raise HTTPException(status_code=404, detail="Service Worker not found")

class IncomingWhatsAppMessage(BaseModel):
    sender_id: str
    sender_name: str
    message: str
    is_group: bool = False
    is_admin: Optional[bool] = False

class BroadcastRequest(BaseModel):
    title: str
    message: str
    target_group: Optional[str] = None
    target_groups: Optional[List[str]] = None

class ChatRequest(BaseModel):
    sender_name: Optional[str] = "Student"
    message: str
    is_admin: Optional[bool] = False

class CustomQARequest(BaseModel):
    question: str
    answer: str
    keywords: Optional[str] = ""
    category: Optional[str] = "custom"

class QuickNoteRequest(BaseModel):
    title: Optional[str] = "CR Quick Note"
    content: str

class UpdateQARequest(BaseModel):
    question: str
    answer: str
    keywords: Optional[str] = ""
    category: Optional[str] = "custom"

class UpdateQuickNoteRequest(BaseModel):
    title: str
    content: str

class UpdateFileInstructionRequest(BaseModel):
    instruction: str

class LogAssessmentRequest(BaseModel):
    course_code: str
    assessment_type: str = "CT"
    number: int = 1
    status: str = "completed"
    scheduled_date: Optional[str] = None
    notes: Optional[str] = ""

class AssessmentPlanRequest(BaseModel):
    plan: str

class TextNoticeDraftRequest(BaseModel):
    raw_text: str
    instruction: Optional[str] = None

class DirectBroadcastRequest(BaseModel):
    title: str = "CR Notice"
    content: str
    target_group: Optional[str] = None
    target_groups: Optional[List[str]] = None

# Group & Bridge Configuration Models
class AddGroupRequest(BaseModel):
    id: Optional[str] = None
    platform: str = "whatsapp" # "whatsapp" or "messenger"
    name: str
    category: str = "subject_specific"
    subject_code: Optional[str] = "All"
    identifier: Optional[str] = ""
    invite_link: Optional[str] = ""
    is_default_target: bool = False
    is_cr_source: bool = False
    is_active: bool = True

class UpdateGroupRequest(BaseModel):
    name: Optional[str] = None
    platform: Optional[str] = None
    category: Optional[str] = None
    subject_code: Optional[str] = None
    identifier: Optional[str] = None
    invite_link: Optional[str] = None
    is_default_target: Optional[bool] = None
    is_cr_source: Optional[bool] = None
    is_active: Optional[bool] = None

class UpdateBridgeRequest(BaseModel):
    cr_source_group_id: Optional[str] = None
    primary_notice_target_id: Optional[str] = None
    auto_relay: Optional[bool] = None

# AI Engine Configuration Models
class UpdateAIActiveRequest(BaseModel):
    provider: str
    model: str

class UpdateAIProviderRequest(BaseModel):
    provider_id: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    default_model: Optional[str] = None
    enabled: Optional[bool] = None

class AddCustomAIRequest(BaseModel):
    provider_id: str
    name: str
    base_url: str
    api_key: str
    default_model: str

class TestAIRequest(BaseModel):
    provider_id: str
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None

class StudentRecordInput(BaseModel):
    roll_no: str
    name: str
    status: str = "P"
    notes: Optional[str] = ""

class AttendanceSubmitRequest(BaseModel):
    course_code: str
    session_date: str
    topic: Optional[str] = ""
    records: List[StudentRecordInput]

class AddStudentRequest(BaseModel):
    roll_no: str
    name: str
    serial_no: Optional[int] = None

class EmailDraftApiRequest(BaseModel):
    recipient_name: str
    recipient_email: str
    topic: str
    context: Optional[str] = ""

class EmailUpdateApiRequest(BaseModel):
    email_id: int
    recipient_name: Optional[str] = None
    recipient_email: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None

class EmailSendApiRequest(BaseModel):
    email_id: int
    recipient_name: Optional[str] = None
    recipient_email: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None

class EmailSmtpConfigRequest(BaseModel):
    smtp_user: str
    smtp_pass: str

def generate_session_token(password: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), password.encode(), hashlib.sha256).hexdigest()

def is_authenticated(request: Request) -> bool:
    token = request.cookies.get("session_token")
    valid = generate_session_token(settings.DASHBOARD_PASSWORD)
    if token == valid:
        return True
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        bearer = auth_header.split(" ")[1]
        return bearer in [settings.SECRET_KEY, settings.DASHBOARD_PASSWORD]
    return False

def require_auth(request: Request):
    """Enforces authentication via session cookie or Authorization Bearer header."""
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized: Please log in with dashboard password.")
    return True

class LoginRequest(BaseModel):
    password: str

@app.get("/login", response_class=HTMLResponse)
def get_login_page(request: Request):
    if is_authenticated(request):
        return RedirectResponse(url="/dashboard")
    login_path = os.path.join(os.path.dirname(__file__), "templates", "login.html")
    if os.path.exists(login_path):
        with open(login_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Login Page</h1>"

@app.post("/api/login")
def login(req: LoginRequest, response: Response):
    if req.password == settings.DASHBOARD_PASSWORD:
        token = generate_session_token(settings.DASHBOARD_PASSWORD)
        response.set_cookie(
            key="session_token",
            value=token,
            httponly=True,
            max_age=30 * 24 * 3600, # 30 days persistent session on phone/PC
            samesite="lax"
        )
        return {"status": "success"}
    raise HTTPException(status_code=401, detail="Incorrect password. Access denied.")

@app.get("/logout")
@app.post("/api/logout")
def logout(response: Response):
    res = RedirectResponse(url="/login")
    res.delete_cookie("session_token")
    return res

@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
def get_dashboard(request: Request):
    if not is_authenticated(request):
        return RedirectResponse(url="/login")
    dashboard_path = os.path.join(os.path.dirname(__file__), "templates", "dashboard.html")
    if os.path.exists(dashboard_path):
        with open(dashboard_path, "r", encoding="utf-8") as f:
            return f.read()
    return f"<h1>{settings.ADMIN_NAME}'s AI Assistant Control Center is Online</h1>"

@app.get("/api/announcements/pending", dependencies=[Depends(require_auth)])
def get_pending_announcements():
    import sqlite3
    from core.database import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, content, source, target_group, created_at FROM announcements WHERE status = 'pending_approval' ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return {
        "pending": [
            {"id": r[0], "title": r[1], "content": r[2], "source": r[3], "target_group": r[4], "created_at": r[5]}
            for r in rows
        ]
    }

class QueueNoticeRequest(BaseModel):
    title: str
    message: str
    target_group: Optional[str] = None
    target_groups: Optional[List[str]] = None

@app.post("/api/announcements/queue", dependencies=[Depends(require_auth)])
def queue_notice_announcement(req: QueueNoticeRequest):
    from modules.config.group_manager import group_manager
    target = req.target_group
    if not target and req.target_groups and len(req.target_groups) > 0:
        target = ",".join(req.target_groups)
    if not target:
        target = group_manager.get_primary_notice_target()
    ann_id = save_announcement(
        title=req.title,
        content=req.message,
        source="schedule_notice",
        target_group=target,
        status="pending_approval"
    )
    return {"status": "queued", "announcement_id": ann_id}

class CalendarOverrideRequest(BaseModel):
    title: str
    event_type: str = "custom"
    start_date: str # YYYY-MM-DD
    end_date: str   # YYYY-MM-DD
    classes_suspended: bool = True
    description: str = ""

class SheetConfigUpdate(BaseModel):
    sheet_id: Optional[str] = None
    gid_routine: Optional[str] = None
    gid_changes: Optional[str] = None
    gid_faculty: Optional[str] = None
    gid_crs: Optional[str] = None

class EditDraftRequest(BaseModel):
    announcement_id: int
    content: str

class ApproveAnnouncementRequest(BaseModel):
    target_groups: Optional[List[str]] = None
    target_group: Optional[str] = None
    edited_content: Optional[str] = None

@app.get("/api/academic/attendance", dependencies=[Depends(require_auth)])
def get_attendance():
    from modules.academic.portal_scraper import portal_scraper
    records = portal_scraper.get_latest_attendance()
    return {"records": records}

@app.post("/api/academic/scrape-portal", dependencies=[Depends(require_auth)])
async def trigger_portal_scrape():
    from modules.academic.portal_scraper import portal_scraper
    records = await portal_scraper.scrape_portal_attendance()
    return {"status": "success", "records": records}

@app.post("/api/academic/send-absent-alert", dependencies=[Depends(require_auth)])
async def send_absent_alert():
    from modules.academic.portal_scraper import portal_scraper, ADMIN_EMAIL
    from modules.mailer.email_service import email_service
    records = portal_scraper.get_latest_attendance()
    absent_lines = []
    for r in records:
        if r.get("absents"):
            for a in r["absents"]:
                absent_lines.append(f"• {r['course_code']}: Absent on {a['date']} ({a.get('day','')}) at {a.get('time','')} with {a.get('teacher','')}")
    
    if not absent_lines:
        return {"status": "info", "detail": "No absent records logged on the student portal. You have 100% attendance!"}

    target_email = settings.ADMIN_EMAIL or ADMIN_EMAIL
    if not target_email:
        return {"status": "failed", "detail": "Admin email not configured in .env."}

    subject = f"📊 Full Attendance & Absentee Status Report - {settings.UNIVERSITY_NAME}"
    body = (
        f"Dear {settings.ADMIN_NAME} (Student ID: {settings.ADMIN_STUDENT_ID}),\n\n"
        f"Here is your official absentee report from the Student Portal:\n\n" +
        "\n".join(absent_lines) +
        "\n\nCourse Summary:\n" +
        "\n".join([f"• {r['course_code']}: {r['percentage']}% ({r['attended_classes']}/{r['total_classes']} classes)" for r in records]) +
        "\n\nPlease ensure you maintain 75%+ attendance to avoid Non-Collegiate / Discollegiate penalties before semester finals."
    )

    success, msg = email_service.send_direct_email(target_email, subject, body)
    return {"status": "sent" if success else "failed", "detail": msg}

@app.get("/api/academic/calendar", dependencies=[Depends(require_auth)])
def get_calendar():
    from modules.academic.academic_calendar import academic_calendar
    return {"events": academic_calendar.get_all_events()}

@app.post("/api/academic/calendar/override", dependencies=[Depends(require_auth)])
def add_calendar_override(req: CalendarOverrideRequest):
    from modules.academic.academic_calendar import academic_calendar
    new_id = academic_calendar.add_custom_override(
        title=req.title,
        event_type=req.event_type,
        start_date=req.start_date,
        end_date=req.end_date,
        classes_suspended=req.classes_suspended,
        description=req.description
    )
    return {"status": "created", "id": new_id}

@app.delete("/api/academic/calendar/override/{event_id}", dependencies=[Depends(require_auth)])
def delete_calendar_override(event_id: int):
    from modules.academic.academic_calendar import academic_calendar
    success = academic_calendar.delete_custom_override(event_id)
    return {"status": "deleted" if success else "not_found"}

# === CT, Quiz & Assessment Planner Endpoints ===

@app.get("/api/academic/assessments/summary", dependencies=[Depends(require_auth)])
def get_assessments_summary():
    from modules.academic.assessment_planner import assessment_planner
    return {
        "summary": assessment_planner.get_assessment_summary(),
        "records": assessment_planner.list_assessments(),
        "saved_plan": assessment_planner.get_saved_plan()
    }

@app.post("/api/academic/assessments/log", dependencies=[Depends(require_auth)])
def log_assessment_record(req: LogAssessmentRequest):
    from modules.academic.assessment_planner import assessment_planner
    ass_id = assessment_planner.log_assessment(
        course_code=req.course_code,
        assessment_type=req.assessment_type,
        number=req.number,
        status=req.status,
        scheduled_date=req.scheduled_date,
        notes=req.notes or ""
    )
    return {"status": "success", "id": ass_id}

@app.delete("/api/academic/assessments/{ass_id}", dependencies=[Depends(require_auth)])
def delete_assessment_record(ass_id: int):
    from modules.academic.assessment_planner import assessment_planner
    success = assessment_planner.delete_assessment(ass_id)
    return {"status": "deleted" if success else "not_found"}

@app.get("/api/academic/assessments/plan", dependencies=[Depends(require_auth)])
def get_assessment_plan():
    from modules.academic.assessment_planner import assessment_planner
    return {"plan": assessment_planner.get_saved_plan()}

@app.post("/api/academic/assessments/plan", dependencies=[Depends(require_auth)])
def update_assessment_plan(req: AssessmentPlanRequest):
    from modules.academic.assessment_planner import assessment_planner
    assessment_planner.save_plan(req.plan)
    return {"status": "saved", "plan": req.plan}

@app.post("/api/academic/assessments/broadcast", dependencies=[Depends(require_auth)])
async def broadcast_assessment_plan(req: AssessmentPlanRequest):
    from modules.academic.assessment_planner import assessment_planner
    from modules.notifier.whatsapp_client import whatsapp_client
    from core.database import save_announcement
    
    plan_text = req.plan.strip()
    if not plan_text:
        plan_text = assessment_planner.get_saved_plan()
    
    assessment_planner.save_plan(plan_text)
    
    save_announcement(
        title="CT & Assessment Schedule Plan",
        content=plan_text,
        source="admin_dashboard_planner",
        target_group=settings.WHATSAPP_NOTICE_GROUP_ID,
        status="broadcasted"
    )
    success = await whatsapp_client.send_group_message(settings.WHATSAPP_NOTICE_GROUP_ID, plan_text)
    return {"status": "success" if success else "failed", "broadcasted": plan_text}

@app.get("/api/config/sheets", dependencies=[Depends(require_auth)])
def get_sheet_config():
    return {
        "google_sheet_id": settings.GOOGLE_SHEET_ID,
        "gid_routine": settings.GID_ROUTINE,
        "gid_changes": settings.GID_CHANGES,
        "gid_faculty": settings.GID_FACULTY,
        "gid_crs": settings.GID_CRS
    }

@app.post("/api/config/sheets", dependencies=[Depends(require_auth)])
def update_sheet_config(req: SheetConfigUpdate):
    if req.sheet_id: settings.GOOGLE_SHEET_ID = req.sheet_id
    if req.gid_routine: settings.GID_ROUTINE = req.gid_routine
    if req.gid_changes: settings.GID_CHANGES = req.gid_changes
    if req.gid_faculty: settings.GID_FACULTY = req.gid_faculty
    if req.gid_crs: settings.GID_CRS = req.gid_crs

    stats = sheet_sync.sync_all()
    return {"status": "updated", "stats": stats}

@app.post("/api/announcements/edit-draft", dependencies=[Depends(require_auth)])
def edit_announcement_draft(req: EditDraftRequest):
    import sqlite3
    from core.database import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE announcements SET content = ? WHERE id = ? AND status = 'pending_approval'", (req.content, req.announcement_id))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return {"status": "updated" if affected > 0 else "not_found"}

# === Knowledge Base, Local Documents & Custom QA Endpoints ===

@app.get("/api/knowledge/files", dependencies=[Depends(require_auth)])
def get_knowledge_files():
    from modules.rag.knowledge_base import knowledge_base
    return {"files": knowledge_base.list_files()}

@app.post("/api/knowledge/upload", dependencies=[Depends(require_auth)])
async def upload_knowledge_file(
    file: UploadFile = File(...),
    instruction: Optional[str] = Form(None)
):
    from modules.rag.knowledge_base import knowledge_base
    filename = file.filename
    content = await file.read()
    dest = knowledge_base.add_file(filename, content, instruction=instruction)
    return {"status": "uploaded", "filename": filename, "path": dest, "instruction": instruction}

@app.delete("/api/knowledge/files/{filename}", dependencies=[Depends(require_auth)])
def delete_knowledge_file(filename: str):
    from modules.rag.knowledge_base import knowledge_base
    success = knowledge_base.delete_file(filename)
    return {"status": "deleted" if success else "not_found"}

@app.post("/api/knowledge/files/{filename}/toggle", dependencies=[Depends(require_auth)])
def toggle_knowledge_file(filename: str):
    from modules.rag.knowledge_base import knowledge_base
    new_status = knowledge_base.toggle_file_active(filename)
    return {"status": "success", "filename": filename, "is_active": new_status}

@app.get("/api/knowledge/qa", dependencies=[Depends(require_auth)])
def get_custom_qas():
    from core.database import get_all_custom_qa
    return {"qas": get_all_custom_qa()}

@app.post("/api/knowledge/qa", dependencies=[Depends(require_auth)])
def create_custom_qa(req: CustomQARequest):
    from core.database import add_custom_qa
    from modules.rag.knowledge_base import knowledge_base
    qa_id = add_custom_qa(
        question=req.question,
        answer=req.answer,
        keywords=req.keywords or req.question,
        category=req.category or "custom"
    )
    knowledge_base.load_all()
    return {"status": "created", "id": qa_id}

@app.delete("/api/knowledge/qa/{qa_id}", dependencies=[Depends(require_auth)])
def remove_custom_qa(qa_id: int):
    from core.database import delete_custom_qa
    from modules.rag.knowledge_base import knowledge_base
    success = delete_custom_qa(qa_id)
    knowledge_base.load_all()
    return {"status": "deleted" if success else "not_found"}

@app.put("/api/knowledge/qa/{qa_id}", dependencies=[Depends(require_auth)])
def update_qa(qa_id: int, req: UpdateQARequest):
    from core.database import update_custom_qa
    from modules.rag.knowledge_base import knowledge_base
    success = update_custom_qa(
        qa_id=qa_id,
        question=req.question,
        answer=req.answer,
        keywords=req.keywords or req.question,
        category=req.category or "custom"
    )
    knowledge_base.load_all()
    return {"status": "updated" if success else "not_found"}

@app.get("/api/knowledge/quick-notes", dependencies=[Depends(require_auth)])
def get_quick_notes():
    from modules.rag.knowledge_base import knowledge_base
    return {"notes": knowledge_base.list_quick_notes()}

@app.post("/api/knowledge/quick-note", dependencies=[Depends(require_auth)])
def add_quick_note(req: QuickNoteRequest):
    from modules.rag.knowledge_base import knowledge_base
    fpath = knowledge_base.save_quick_note(note_text=req.content, title=req.title or "CR Quick Note")
    return {"status": "saved", "path": fpath}

@app.put("/api/knowledge/quick-notes/{note_id}", dependencies=[Depends(require_auth)])
def update_quick_note(note_id: int, req: UpdateQuickNoteRequest):
    from modules.rag.knowledge_base import knowledge_base
    success = knowledge_base.update_quick_note(note_id, req.title, req.content)
    return {"status": "updated" if success else "not_found"}

@app.delete("/api/knowledge/quick-notes/{note_id}", dependencies=[Depends(require_auth)])
def delete_quick_note(note_id: int):
    from modules.rag.knowledge_base import knowledge_base
    success = knowledge_base.delete_quick_note(note_id)
    return {"status": "deleted" if success else "not_found"}

@app.put("/api/knowledge/files/{filename}/instruction", dependencies=[Depends(require_auth)])
def update_file_instruction(filename: str, req: UpdateFileInstructionRequest):
    from modules.rag.knowledge_base import knowledge_base
    success = knowledge_base.update_file_instruction(filename, req.instruction)
    return {"status": "updated" if success else "not_found"}

@app.post("/api/knowledge/resync", dependencies=[Depends(require_auth)])
def resync_knowledge():
    from modules.rag.knowledge_base import knowledge_base
    knowledge_base.load_all()
    return {"status": "resynced", "documents_count": len(knowledge_base.documents)}

BOT_CONFIG_PATH = os.path.join(settings.DATA_DIR, "bot_config.json")

def read_bot_config_file() -> dict:
    try:
        if os.path.exists(BOT_CONFIG_PATH):
            with open(BOT_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"auto_reply_enabled": True}

def write_bot_config_file(data: dict):
    try:
        os.makedirs(os.path.dirname(BOT_CONFIG_PATH), exist_ok=True)
        with open(BOT_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving bot_config.json: {e}")

@app.get("/api/whatsapp/toggle-bot", dependencies=[Depends(require_auth)])
async def get_bot_toggle():
    import httpx
    cfg = read_bot_config_file()
    bridge_info = {"connected": False, "registered": False}
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get("http://localhost:3001/api/status", timeout=2)
            if res.status_code == 200:
                bridge_info = res.json()
    except Exception:
        pass
    return {
        "auto_reply_enabled": cfg.get("auto_reply_enabled", True),
        "connected": bridge_info.get("connected", False),
        "registered": bridge_info.get("registered", False),
        "user": bridge_info.get("user")
    }

@app.post("/api/whatsapp/toggle-bot", dependencies=[Depends(require_auth)])
async def toggle_bot():
    import httpx
    cfg = read_bot_config_file()
    new_state = not cfg.get("auto_reply_enabled", True)
    cfg["auto_reply_enabled"] = new_state
    cfg["updated_at"] = datetime.now().isoformat()
    write_bot_config_file(cfg)

    try:
        async with httpx.AsyncClient() as client:
            headers = {"X-Bridge-Token": settings.SECRET_KEY}
            res = await client.post("http://localhost:3001/api/bot-toggle", json={"enabled": new_state}, headers=headers, timeout=2)
            if res.status_code == 200:
                return res.json()
    except Exception as e:
        print(f"Node WhatsApp bridge offline during toggle (persisted to disk): {e}")

    return {"auto_reply_enabled": new_state}

@app.get("/api/academic/export-classes", dependencies=[Depends(require_auth)])
def export_classes_csv():
    from modules.academic.class_tracker import class_tracker
    csv_path = class_tracker.export_csv()
    return FileResponse(csv_path, media_type="text/csv", filename="class_history.csv")

@app.get("/api/status", dependencies=[Depends(require_auth)])
def get_status():
    return {
        "last_sheet_sync": sheet_sync.last_sync.isoformat() if sheet_sync.last_sync else None,
        "total_routine_slots": len(sheet_sync.routine_slots),
        "total_faculty": len(sheet_sync.faculty_map),
        "total_crs": len(sheet_sync.cr_map),
        "knowledge_documents": len(knowledge_base.documents)
    }

@app.post("/api/whatsapp/incoming")
async def handle_whatsapp_incoming(payload: IncomingWhatsAppMessage, request: Request):
    """Webhook invoked strictly by Node.js WhatsApp Bridge with token verification."""
    token = request.headers.get("X-Bridge-Token")
    client_host = request.client.host if request.client else ""
    is_local = client_host in ["127.0.0.1", "localhost", "::1"]
    
    if not is_local and token != settings.SECRET_KEY:
        raise HTTPException(status_code=403, detail="Forbidden: Unauthorized bridge webhook invocation.")

    sender_clean = payload.sender_id.replace("@s.whatsapp.net", "").replace("+", "").split("@")[0]
    admin_clean = settings.ADMIN_PHONE.replace("+", "")
    
    # Strict admin check: Only trusted if bridge verified it AND it comes from admin phone or linked account
    is_admin = bool(payload.is_admin and (sender_clean == admin_clean or "Admin" in payload.sender_name or "@lid" in payload.sender_id))

    reply, is_fallback = gemini_brain.process_query(
        sender_id=payload.sender_id,
        sender_name=payload.sender_name,
        message=payload.message,
        is_admin=is_admin
    )

    return {
        "status": "success",
        "reply": reply,
        "is_fallback": is_fallback
    }

@app.post("/api/chat")
def test_chat(req: ChatRequest, request: Request):
    """Interactive testing endpoint for CLI / Web playground."""
    admin_allowed = req.is_admin or False
    if admin_allowed and not is_authenticated(request):
        admin_allowed = False # Downgrade to regular student if unauthenticated!

    reply, is_fallback = gemini_brain.process_query(
        sender_id="test_user",
        sender_name=req.sender_name or "Student",
        message=req.message,
        is_admin=admin_allowed
    )
    return {
        "reply": reply,
        "is_fallback": is_fallback
    }

@app.get("/api/routine/{day}")
def get_routine_day(day: str, section: Optional[str] = None):
    sec = section or settings.SECTION_NAME
    msg = sheet_sync.format_routine_message(day, section=sec)
    slots = sheet_sync.get_routine_for_day(day, section=sec)
    return {
        "day": day,
        "section": sec,
        "notice_message": msg,
        "raw_slots": [s.model_dump() for s in slots]
    }

@app.post("/api/broadcast", dependencies=[Depends(require_auth)])
async def broadcast_notice(req: BroadcastRequest):
    """Broadcast an announcement to selected groups or Primary Notice Group."""
    from modules.config.group_manager import group_manager
    if req.target_groups and len(req.target_groups) > 0:
        res = await group_manager.broadcast_to_selected_groups(
            target_group_ids=req.target_groups,
            message=req.message,
            title=req.title
        )
        return {
            "status": "success",
            "broadcast_details": res,
            "message": req.message
        }
    target = req.target_group or group_manager.get_primary_notice_target()
    save_announcement(
        title=req.title,
        content=req.message,
        source="admin_manual",
        target_group=target,
        status="broadcasted"
    )
    success = await whatsapp_client.send_group_message(target, req.message)
    return {
        "status": "success" if success else "failed",
        "broadcasted_to": target,
        "message": req.message
    }

@app.post("/api/upload-screenshot", dependencies=[Depends(require_auth)])
async def upload_screenshot(file: UploadFile = File(...), instruction: Optional[str] = Form(None)):
    """Upload notice screenshot, extract with Gemini 3.8 Flash Vision, and queue for CR's approval."""
    from modules.vision.screenshot_parser import screenshot_parser
    contents = await file.read()
    ann_id, draft = screenshot_parser.parse_and_draft_announcement(contents, custom_instruction=instruction)
    return {
        "status": "pending_approval",
        "announcement_id": ann_id,
        "draft_notice": draft,
        "instruction": f"Review this draft. Send '!approve {ann_id}' to broadcast or '!reject {ann_id}' to discard."
    }

@app.post("/api/approve-announcement/{ann_id}", dependencies=[Depends(require_auth)])
async def approve_announcement(ann_id: int, req: Optional[ApproveAnnouncementRequest] = None):
    """Approve a queued announcement and post it to selected groups or WhatsApp Notice Group."""
    from modules.vision.screenshot_parser import screenshot_parser
    from modules.config.group_manager import group_manager
    import sqlite3
    from core.database import DB_PATH

    if req and req.edited_content:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE announcements SET content = ? WHERE id = ? AND status = 'pending_approval'", (req.edited_content, ann_id))
        conn.commit()
        conn.close()

    content = screenshot_parser.approve_and_broadcast(ann_id)
    if not content:
        raise HTTPException(status_code=404, detail="Announcement not found in pending approval queue.")

    if req and req.target_groups and len(req.target_groups) > 0:
        res = await group_manager.broadcast_to_selected_groups(
            target_group_ids=req.target_groups,
            message=content,
            title="CR Announcement"
        )
        return {
            "status": "broadcasted",
            "announcement_id": ann_id,
            "broadcast_details": res,
            "target_groups": req.target_groups,
            "content": content
        }

    target = (req.target_group if req else None) or group_manager.get_primary_notice_target()
    success = await whatsapp_client.send_group_message(target, content)
    return {
        "status": "broadcasted" if success else "failed",
        "announcement_id": ann_id,
        "target_group": target,
        "content": content
    }

# === Text-to-Notice Drafter & Direct Broadcast Endpoints ===

@app.post("/api/notices/draft-text", dependencies=[Depends(require_auth)])
def draft_notice_from_text(req: TextNoticeDraftRequest):
    """Draft a polished WhatsApp announcement from raw notes or instructions."""
    from modules.vision.screenshot_parser import screenshot_parser
    ann_id, draft = screenshot_parser.draft_from_text(req.raw_text, custom_instruction=req.instruction, auto_queue=True)
    return {
        "status": "pending_approval",
        "announcement_id": ann_id,
        "draft_notice": draft
    }

@app.post("/api/notices/broadcast-direct", dependencies=[Depends(require_auth)])
async def broadcast_notice_direct(req: DirectBroadcastRequest):
    """Broadcast an announcement directly to selected groups or Primary Notice Group."""
    from modules.config.group_manager import group_manager
    if req.target_groups and len(req.target_groups) > 0:
        res = await group_manager.broadcast_to_selected_groups(
            target_group_ids=req.target_groups,
            message=req.content,
            title=req.title
        )
        return {
            "status": "success",
            "broadcast_details": res,
            "content": req.content
        }
    target = req.target_group or group_manager.get_primary_notice_target()
    save_announcement(
        title=req.title,
        content=req.content,
        source="admin_dashboard_direct",
        target_group=target,
        status="broadcasted"
    )
    success = await whatsapp_client.send_group_message(target, req.content)
    return {
        "status": "success" if success else "failed",
        "target_group": target,
        "content": req.content
    }

# === Class Attendance Management Endpoints ===

@app.get("/api/attendance/students", dependencies=[Depends(require_auth)])
def get_attendance_students():
    """Returns the batch student roster."""
    from modules.academic.student_roster import student_roster
    return {"students": student_roster.get_students()}

@app.post("/api/attendance/students", dependencies=[Depends(require_auth)])
def add_attendance_student(req: AddStudentRequest):
    """Adds a new student to the batch roster."""
    from modules.academic.student_roster import student_roster
    new_id = student_roster.add_student(req.roll_no, req.name, req.serial_no)
    return {"status": "created", "id": new_id}

@app.get("/api/attendance/sessions", dependencies=[Depends(require_auth)])
def list_attendance_sessions():
    """Lists past attendance sessions."""
    from modules.academic.student_roster import student_roster
    return {"sessions": student_roster.list_sessions()}

@app.get("/api/attendance/sessions/{session_id}", dependencies=[Depends(require_auth)])
def get_attendance_session_detail(session_id: int):
    """Returns details and student list for a specific attendance session."""
    from modules.academic.student_roster import student_roster
    details = student_roster.get_session_details(session_id)
    if not details:
        raise HTTPException(status_code=404, detail="Attendance session not found.")
    return details

@app.post("/api/attendance/submit", dependencies=[Depends(require_auth)])
def submit_attendance_session(req: AttendanceSubmitRequest):
    """Saves daily class attendance records."""
    from modules.academic.student_roster import student_roster
    recs = [r.model_dump() for r in req.records]
    sess = student_roster.submit_attendance_session(
        course_code=req.course_code,
        session_date=req.session_date,
        topic=req.topic or "",
        records=recs
    )
    return {"status": "success", "session": sess}

@app.delete("/api/attendance/sessions/{session_id}", dependencies=[Depends(require_auth)])
def delete_attendance_session(session_id: int):
    """Deletes an attendance session."""
    from modules.academic.student_roster import student_roster
    success = student_roster.delete_session(session_id)
    return {"status": "deleted" if success else "not_found"}

@app.post("/api/attendance/broadcast/{session_id}", dependencies=[Depends(require_auth)])
async def broadcast_attendance_session(session_id: int):
    """Formats and broadcasts class attendance summary to WhatsApp Notice Group."""
    from modules.academic.student_roster import student_roster
    summary = student_roster.format_whatsapp_summary(session_id)
    save_announcement(
        title=f"Class Attendance Report (Session #{session_id})",
        content=summary,
        source="admin_dashboard_attendance",
        target_group=settings.WHATSAPP_NOTICE_GROUP_ID,
        status="broadcasted"
    )
    success = await whatsapp_client.send_group_message(settings.WHATSAPP_NOTICE_GROUP_ID, summary)
    return {"status": "success" if success else "failed", "broadcasted_text": summary}

@app.get("/api/attendance/export/{session_id}", dependencies=[Depends(require_auth)])
def export_attendance_session(session_id: int):
    """Exports single attendance session to CSV."""
    from modules.academic.student_roster import student_roster
    fpath = student_roster.export_session_csv(session_id)
    if not fpath or not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail="Attendance session not found.")
    return FileResponse(fpath, media_type="text/csv", filename=os.path.basename(fpath))

@app.get("/api/attendance/export-all", dependencies=[Depends(require_auth)])
def export_all_attendance():
    """Exports full semester attendance matrix to CSV."""
    from modules.academic.student_roster import student_roster
    fpath = student_roster.export_all_sessions_csv()
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail="No attendance sessions to export.")
    return FileResponse(fpath, media_type="text/csv", filename="batch_attendance_full_matrix.csv")

# === Dedicated Academic Email Secretary Endpoints ===

@app.get("/api/academic/faculties", dependencies=[Depends(require_auth)])
def get_faculties_directory():
    """Returns sorted list of faculties: Section 2A faculties, Head, Coordinator, and department teachers."""
    import json
    cache_path = os.path.join(settings.DATA_DIR, "sheet_cache.json")
    if not os.path.exists(cache_path):
        return {"faculties": [], "total": 0}

    with open(cache_path, "r", encoding="utf-8") as f:
        cache = json.load(f)

    faculties = cache.get("faculty", {})
    routine = cache.get("routine", [])

    sec2a_courses = {}
    for r in routine:
        sec = r.get("section", "")
        if "2A" in sec:
            init = r.get("faculty_initial", "").strip()
            course = r.get("course_code", "").strip()
            if init and init != "Faculty":
                if init not in sec2a_courses:
                    sec2a_courses[init] = set()
                sec2a_courses[init].add(course)

    output = []
    for init, fac in faculties.items():
        is_head = init == "FI"
        is_coord = init == "FHM"
        is_2a = init in sec2a_courses or is_head or is_coord

        role = "Department Faculty"
        if is_head:
            role = "Head of Department (HOD)"
        elif is_coord:
            role = "Batch Coordinator"
        elif is_2a:
            role = "Section 2A Course Teacher"

        output.append({
            "initial": init,
            "name": fac.get("name", ""),
            "designation": fac.get("designation", ""),
            "email": fac.get("email", ""),
            "phone": fac.get("phone", ""),
            "role": role,
            "is_2a": is_2a,
            "courses_2a": sorted(list(sec2a_courses.get(init, [])))
        })

    # Sort Section 2A & Key Roles to the very top
    output.sort(key=lambda x: (
        not x["is_2a"],
        x["role"] != "Head of Department (HOD)",
        x["role"] != "Batch Coordinator",
        x["name"]
    ))
    return {"faculties": output, "total": len(output)}

@app.get("/api/admin/info")
def get_admin_info():
    """Returns administrator profile metadata for dynamic dashboard rendering."""
    return {
        "admin_name": settings.ADMIN_NAME,
        "admin_student_id": settings.ADMIN_STUDENT_ID,
        "admin_phone": settings.ADMIN_PHONE,
        "admin_email": settings.ADMIN_EMAIL,
        "batch_name": settings.BATCH_NAME,
        "section_name": settings.SECTION_NAME,
        "university_name": settings.UNIVERSITY_NAME,
        "department_name": settings.DEPARTMENT_NAME
    }

@app.get("/api/mailer/status", dependencies=[Depends(require_auth)])
def get_mailer_status():
    from modules.mailer.email_service import email_service
    smtp_user = email_service.current_smtp_user
    smtp_pass = email_service.current_smtp_pass
    admin_mail = settings.ADMIN_EMAIL or smtp_user
    return {
        "smtp_configured": bool(smtp_user and smtp_pass),
        "smtp_user": smtp_user or admin_mail,
        "sender_name": f"{settings.ADMIN_NAME} (CR {settings.SECTION_NAME})",
        "sender_email": smtp_user or admin_mail
    }

@app.post("/api/mailer/draft", dependencies=[Depends(require_auth)])
def draft_email_api(req: EmailDraftApiRequest):
    """Generates an academic email draft from topic and admin context."""
    from modules.mailer.email_service import email_service
    draft = email_service.draft_email_structured(
        recipient_query=req.recipient_email or req.recipient_name,
        topic=req.topic,
        extra_details=req.context or "",
        recipient_name=req.recipient_name,
        recipient_email=req.recipient_email
    )
    return {"status": "success", "draft": draft}

@app.post("/api/mailer/update", dependencies=[Depends(require_auth)])
def update_draft_api(req: EmailUpdateApiRequest):
    """Updates an existing draft with CR's manual edits before sending."""
    from modules.mailer.email_service import email_service
    success = email_service.update_draft_email(
        email_id=req.email_id,
        recipient_email=req.recipient_email,
        recipient_name=req.recipient_name,
        subject=req.subject,
        body=req.body
    )
    if not success:
        raise HTTPException(status_code=404, detail="Email draft not found or already sent.")
    return {"status": "success", "message": f"Draft #{req.email_id} updated successfully."}

@app.post("/api/mailer/send", dependencies=[Depends(require_auth)])
def send_email_api(req: EmailSendApiRequest):
    """Approves and dispatches the email via SMTP (or simulation mode)."""
    from modules.mailer.email_service import email_service
    if req.recipient_email and req.subject and req.body:
        email_service.update_draft_email(
            email_id=req.email_id,
            recipient_email=req.recipient_email,
            recipient_name=req.recipient_name or req.recipient_email,
            subject=req.subject,
            body=req.body
        )
    success, message = email_service.send_approved_email(req.email_id)
    return {
        "status": "sent" if success else "failed",
        "message": message,
        "email_id": req.email_id
    }

@app.post("/api/mailer/cancel/{email_id}", dependencies=[Depends(require_auth)])
def cancel_email_api(email_id: int):
    from modules.mailer.email_service import email_service
    success = email_service.cancel_email(email_id)
    return {"status": "cancelled" if success else "failed"}

@app.get("/api/mailer/history", dependencies=[Depends(require_auth)])
def get_email_history_api():
    from modules.mailer.email_service import email_service
    return {"history": email_service.get_recent_emails(20)}

@app.post("/api/mailer/config-smtp", dependencies=[Depends(require_auth)])
def config_smtp_api(req: EmailSmtpConfigRequest):
    """Saves SMTP credentials into .env and updates runtime environment."""
    user = req.smtp_user.strip()
    pwd = req.smtp_pass.strip().replace(" ", "")
    if not user or not pwd:
        raise HTTPException(status_code=400, detail="SMTP username and password required.")

    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".env"))
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    user_found = False
    pass_found = False
    new_lines = []
    for line in lines:
        if line.startswith("SMTP_USER="):
            new_lines.append(f"SMTP_USER={user}\n")
            user_found = True
        elif line.startswith("SMTP_PASS="):
            new_lines.append(f"SMTP_PASS={pwd}\n")
            pass_found = True
        else:
            new_lines.append(line)

    if not user_found:
        new_lines.append(f"SMTP_USER={user}\n")
    if not pass_found:
        new_lines.append(f"SMTP_PASS={pwd}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    os.environ["SMTP_USER"] = user
    os.environ["SMTP_PASS"] = pwd
    from modules.mailer.email_service import email_service
    email_service.smtp_user = user
    email_service.smtp_pass = pwd

    return {"status": "success", "message": f"SMTP configured for {user}!"}

# === Messenger Bridge Webhooks (Hardened with Auth Verification) ===

class MessengerMessage(BaseModel):
    sender_name: str = "CR Group Member"
    message_text: str

class MessengerImagePayload(BaseModel):
    image_base64: str
    caption: Optional[str] = ""
    sender_name: Optional[str] = "Coordinator / CR Group"

@app.post("/api/messenger/incoming")
async def handle_messenger_incoming(payload: MessengerMessage, request: Request):
    """Webhook invoked by the Messenger bridge when a new message arrives in the CR group."""
    token = request.headers.get("X-Bridge-Token")
    client_host = request.client.host if request.client else ""
    is_local = client_host in ["127.0.0.1", "localhost", "::1"]
    if not is_local and token != settings.SECRET_KEY:
        raise HTTPException(status_code=403, detail="Forbidden: Unauthorized bridge webhook invocation.")

    from modules.bridge.messenger_filter import messenger_filter
    was_relayed, details = await messenger_filter.relay_if_notice(
        sender_name=payload.sender_name,
        message_text=payload.message_text,
        auto_broadcast=settings.MESSENGER_AUTO_RELAY
    )
    return {
        "status": "success",
        "was_relayed": was_relayed,
        "details": details
    }

@app.post("/api/messenger/incoming-image")
async def handle_messenger_incoming_image(payload: MessengerImagePayload, request: Request):
    """Webhook invoked by the Messenger bridge when a photo/screenshot notice is posted in the CR group."""
    token = request.headers.get("X-Bridge-Token")
    client_host = request.client.host if request.client else ""
    is_local = client_host in ["127.0.0.1", "localhost", "::1"]
    if not is_local and token != settings.SECRET_KEY:
        raise HTTPException(status_code=403, detail="Forbidden: Unauthorized bridge webhook invocation.")

    import base64
    from modules.bridge.messenger_filter import messenger_filter
    try:
        image_bytes = base64.b64decode(payload.image_base64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64 image data: {e}")

    was_relayed, details = await messenger_filter.relay_image_if_notice(
        image_bytes=image_bytes,
        caption=payload.caption or "",
        sender_name=payload.sender_name or "Coordinator",
        auto_broadcast=settings.MESSENGER_AUTO_RELAY
    )
    return {
        "status": "success",
        "was_relayed": was_relayed,
        "details": details
    }

# ================= Dynamic Group Management Endpoints =================

@app.get("/api/config/groups", dependencies=[Depends(require_auth)])
def get_configured_groups():
    from modules.config.group_manager import group_manager
    return {
        "groups": group_manager.get_groups(),
        "bridge_config": group_manager.get_bridge_config()
    }

@app.post("/api/config/groups", dependencies=[Depends(require_auth)])
def add_new_group(req: AddGroupRequest):
    from modules.config.group_manager import group_manager
    created = group_manager.add_group(req.model_dump())
    return {"status": "success", "group": created}

@app.put("/api/config/groups/{group_id}", dependencies=[Depends(require_auth)])
def update_existing_group(group_id: str, req: UpdateGroupRequest):
    from modules.config.group_manager import group_manager
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    updated = group_manager.update_group(group_id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Group not found.")
    return {"status": "success", "group": updated}

@app.delete("/api/config/groups/{group_id}", dependencies=[Depends(require_auth)])
def delete_existing_group(group_id: str):
    from modules.config.group_manager import group_manager
    ok = group_manager.delete_group(group_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Group not found.")
    return {"status": "success", "deleted_id": group_id}

@app.post("/api/config/bridge", dependencies=[Depends(require_auth)])
def update_bridge_settings(req: UpdateBridgeRequest):
    from modules.config.group_manager import group_manager
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    updated = group_manager.update_bridge_config(updates)
    return {"status": "success", "bridge_config": updated}

# ================= AI Engine Configuration Endpoints =================

@app.get("/api/config/ai", dependencies=[Depends(require_auth)])
def get_ai_configuration():
    from modules.config.ai_manager import ai_manager
    return ai_manager.get_config()

@app.post("/api/config/ai/active", dependencies=[Depends(require_auth)])
def set_active_ai_provider(req: UpdateAIActiveRequest):
    from modules.config.ai_manager import ai_manager
    res = ai_manager.update_active_selection(req.provider, req.model)
    return res

@app.post("/api/config/ai/provider", dependencies=[Depends(require_auth)])
def update_ai_provider(req: UpdateAIProviderRequest):
    from modules.config.ai_manager import ai_manager
    updates = {k: v for k, v in req.model_dump().items() if v is not None and k != "provider_id"}
    res = ai_manager.update_provider_details(req.provider_id, updates)
    return res

@app.post("/api/config/ai/custom", dependencies=[Depends(require_auth)])
def add_custom_ai(req: AddCustomAIRequest):
    from modules.config.ai_manager import ai_manager
    res = ai_manager.add_custom_provider(req.provider_id, req.name, req.base_url, req.api_key, req.default_model)
    return res

@app.post("/api/config/ai/test", dependencies=[Depends(require_auth)])
async def test_ai_connection(req: TestAIRequest):
    from modules.config.ai_manager import ai_manager
    res = await ai_manager.test_provider_connection(req.provider_id, req.model, req.api_key, req.base_url)
    return res

@app.get("/api/ai/usage")
def get_ai_usage_stats():
    """Returns real-time AI quota percentage used, remaining requests, and reset time."""
    from core.quota_tracker import quota_tracker
    return quota_tracker.get_usage_stats()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.APP_HOST, port=settings.APP_PORT, reload=False)
