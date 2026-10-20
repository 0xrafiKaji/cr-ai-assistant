# 🎓 Autonomous AI Class Representative (CR) Assistant Agent

An autonomous, multi-platform AI assistant designed for university Class Representatives (CRs). It handles class routine inquiries, broadcasts announcements, syncs schedules with Google Sheets, drafts formal academic emails, tracks attendance, monitors Messenger CR discussion groups, and operates 24/7 on WhatsApp with human-in-the-loop safeguards.

---

## ✨ Key Capabilities

1. 🤖 **Multi-Provider AI Brain (Hybrid Architecture):**
   - Seamlessly works with **Google Gemini (3.8 Flash / 2.0)**, **Groq LPU (GPT-OSS 120B / Llama 3.3)**, **OpenAI**, **OpenRouter**, or **Local LLMs (Ollama / DeepSeek)**.
   - Dynamic 1-click model switching and real-time daily quota tracker.
   - Intelligent trilingual understanding: native responses in English, Bengali Unicode (বাংলা), or Banglish.

2. 📱 **WhatsApp 24/7 Bridge (Baileys Engine):**
   - Direct QR code pairing via terminal or Web Dashboard.
   - Intelligent auto-replies for student academic queries (routines, exams, rooms, faculty info).
   - Human-in-the-loop AFK detector: stays quiet when the CR is actively chatting; auto-replies politely when the CR is away.
   - Strict admin command authorization for broadcasts, sync, and bot toggles.

3. 💬 **Messenger CR Group Monitor (Vision OCR):**
   - Headless background listener that monitors department discussion groups.
   - Automatically detects official circulars, routine changes, and exam notices posted as images or text.
   - Formats clean, aesthetic WhatsApp broadcast drafts with 1-click approval.

4. 📊 **Google Sheets Live Routine Sync:**
   - Real-time automated sync with Master Google Sheets (Class Routine, Routine Changes, Faculty Directory, CR Contacts).
   - Daily morning routine broadcast (default 6:00 AM) to the class notice group.
   - 5-minute background poller for instant notification of sudden schedule changes or faculty room shifts.

5. 📋 **Batch Attendance & Assessment Planner:**
   - Interactive student attendance logging with 1-click Present/Absent/Late status.
   - Export session attendance records to standard CSV files.
   - Optional automated Student Portal scraper for real-time personal attendance tracking and absentee alerts.

6. ✉️ **Formal Academic Email Drafter:**
   - Generates respectful, formal academic emails to course teachers, coordinators, or HODs from informal bullet points.
   - 1-click dispatch via configured Gmail App Password (SMTP) or direct draft opening in Gmail Web.

7. 🌐 **Modern Liquid Glass Web Dashboard & PWA:**
   - Dark & Light mode with custom themes (Obsidian Dark, Liquid Glass, Cyber Emerald, Royal Indigo, Sunset Glow).
   - Mobile responsive design with Progressive Web App (PWA) support.

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- **Python 3.10+** (Python 3.11+ recommended)
- **Node.js 18+** & `npm`
- (Optional) **Docker** & **Docker Compose**

### 2. Clone the Repository
```bash
git clone <YOUR_PRIVATE_REPO_URL>
cd cr-ai-assistant
```

### 3. Configure Environment Variables
Copy the template configuration file:
```bash
cp .env.example .env
```
Open `.env` and fill in your preferences:
```env
# AI Provider (Get a free key from https://aistudio.google.com/ or https://console.groq.com/)
GEMINI_API_KEY=your_gemini_api_key_here
GROQ_API_KEY=your_groq_api_key_here
AI_PRIMARY_PROVIDER=gemini

# Your Identity as Class Representative
ADMIN_NAME=Your Full Name
ADMIN_PHONE=8801XXXXXXXXX
ADMIN_STUDENT_ID=12345678
ADMIN_EMAIL=your_email@gmail.com
UNIVERSITY_NAME=Your University Name
DEPARTMENT_NAME=Computer Science & Engineering
BATCH_NAME=1st
SECTION_NAME=A

# Web Dashboard Password
DASHBOARD_PASSWORD=your_secure_password
SECRET_KEY=generate_a_random_secret_token

# (Optional) Google Sheet Integration
GOOGLE_SHEET_ID=your_public_google_sheet_id
GID_ROUTINE=0
GID_CHANGES=123456789
GID_FACULTY=987654321
GID_CRS=1122334455

# Target WhatsApp Group
WHATSAPP_NOTICE_GROUP_ID=https://chat.whatsapp.com/YOUR_GROUP_INVITE_CODE
```

### 4. Install Dependencies
```bash
# Python dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Playwright browser binaries (for Vision & Portal scraper)
playwright install chromium

# WhatsApp Bridge dependencies
cd bridges/whatsapp
npm install
cd ../..
```

---

## 🏃 Running the Application

### Option A: 24/7 Background Services (Recommended for Linux/Mac)
To run the server, WhatsApp bridge, and Messenger monitor simultaneously in the background:
```bash
# Start all services
./start_background.sh

# Check live status
./status_background.sh

# Stop all services
./stop_background.sh
```

### Option B: Interactive Launcher Script
```bash
# Start Web Dashboard & Server
./run.sh server

# Start WhatsApp Bridge
./run.sh whatsapp

# Test queries directly via interactive CLI playground
./run.sh cli

# Run automated test suite
./run.sh test
```

### Option C: Docker Deployment
```bash
docker-compose up -d --build
```

---

## 📱 Connecting Platforms & Groups

### 1. Connecting WhatsApp
1. Start the WhatsApp bridge (`npm start` inside `bridges/whatsapp` or `./start_background.sh`).
2. Open the Web Dashboard at `http://localhost:8000` or visit `http://localhost:3001/qr`.
3. Open WhatsApp on your phone ➔ **Settings** ➔ **Linked Devices** ➔ **Link a Device**.
4. Scan the QR code displayed on the screen. The bot will automatically verify and start listening.

### 2. Configuring Target Notice Groups
- Navigate to the **Groups** tab in the Web Dashboard.
- Add your official WhatsApp Announcement Group invite link.
- Specify whether notices should be auto-relayed or held in the approval queue.

### 3. Connecting Messenger CR Discussion Group (Optional)
1. Run the interactive login script once:
   ```bash
   ./run.sh messenger-login
   ```
2. A Chromium browser window will open. Log into your Facebook account and navigate to your Messenger CR discussion thread.
3. Return to the terminal and press `[ENTER]` to persist your session cookies.
4. Future monitor runs will execute completely headless in the background.

---

## 🛡️ Security & Privacy Architecture

- **Zero Secret Commits:** `.env`, authentication tokens, browser profiles, session data (`auth_info_baileys`), and SQLite databases are strictly gitignored.
- **Role-Based Authorization:** Public users can only query general schedules (`!routine`, `!cts`, `!help`). Administrative commands (`!sync`, `!notice`, `!bot on/off`) are strictly restricted to the verified admin phone number and authenticated dashboard session.
- **Prompt Injection Defense:** Strict system boundaries prevent AI jailbreaks and system prompt disclosures.

---

## 📜 License
This project is open-source and available under the [MIT License](LICENSE).
