from pydantic_settings import BaseSettings
from typing import Optional
import os

class Settings(BaseSettings):
    # AI Providers (Hybrid: Gemini + Groq)
    GEMINI_API_KEY: Optional[str] = ""
    GEMINI_MODEL: str = "gemini-3.8-flash"

    GROQ_API_KEY: Optional[str] = ""
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    AI_PRIMARY_PROVIDER: str = "groq"

    # Admin Identity / Class Representative
    ADMIN_NAME: str = "Class Representative"
    ADMIN_PHONE: str = ""
    ADMIN_STUDENT_ID: str = ""
    ADMIN_EMAIL: str = ""
    BATCH_NAME: str = ""
    SECTION_NAME: str = ""
    UNIVERSITY_NAME: str = ""
    DEPARTMENT_NAME: str = ""

    # Google Sheets Configuration
    GOOGLE_SHEET_ID: str = ""
    GID_ROUTINE: str = ""
    GID_CHANGES: str = ""
    GID_FACULTY: str = ""
    GID_CRS: str = ""

    # WhatsApp Bridge
    WHATSAPP_PORT: int = 3001
    WHATSAPP_HOST: str = "127.0.0.1"
    WHATSAPP_BRIDGE_URL: str = "http://localhost:3001"
    WHATSAPP_NOTICE_GROUP_ID: str = ""
    WHATSAPP_INVITE_CODE: str = ""

    # Messenger CR Group Bridge
    MESSENGER_CR_GROUP_URL: str = ""
    MESSENGER_CR_THREAD_ID: str = ""
    MESSENGER_AUTO_RELAY: bool = True

    # Student Portal Scraper (Optional)
    STUDENT_PORTAL_URL: str = ""
    STUDENT_PORTAL_USER: str = ""
    STUDENT_PORTAL_PASS: str = ""

    # SMTP Mailer (Optional)
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASS: str = ""

    # App Config
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    DAILY_ROUTINE_HOUR: int = 6
    DAILY_ROUTINE_MINUTE: int = 0
    SHEET_POLL_INTERVAL_SECONDS: int = 300

    # Security & Dashboard Auth
    DASHBOARD_PASSWORD: str = "admin123"
    SECRET_KEY: str = "cr_ai_assistant_default_secret_key_change_me"

    # Knowledge Base & Storage
    DATA_DIR: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
    KNOWLEDGE_BASE_DIR: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "knowledge_base"))

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
