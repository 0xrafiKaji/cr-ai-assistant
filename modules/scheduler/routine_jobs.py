from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from config.settings import settings
from modules.sheets.sync import sheet_sync
from modules.notifier.whatsapp_client import whatsapp_client
from core.database import record_announced_change, save_announcement

scheduler = AsyncIOScheduler()

async def job_daily_6am_routine():
    """Triggered every day at 6:00 AM to post today's routine."""
    now = datetime.now()
    day_name = now.strftime("%A")
    print(f"⏰ [Scheduler] Running 6:00 AM Daily Routine Broadcaster for {day_name}...")

    # Ensure sheets are synced
    try:
        sheet_sync.sync_all()
    except Exception as e:
        print(f"Warning: Sheet sync failed during 6 AM job: {e}")

    notice_text = sheet_sync.format_routine_message(day_name, section=settings.SECTION_NAME)

    # Save to SQLite
    save_announcement(
        title=f"Daily Routine - {day_name}",
        content=notice_text,
        source="routine_6am",
        target_group=settings.WHATSAPP_NOTICE_GROUP_ID,
        status="broadcasted"
    )

    # Send to WhatsApp Notice Group
    success = await whatsapp_client.send_group_message(
        group_id=settings.WHATSAPP_NOTICE_GROUP_ID,
        message=notice_text
    )
    if success:
        print(f"✅ Daily {day_name} routine broadcasted to WhatsApp Notice Group.")
    else:
        print(f"⚠️ WhatsApp bridge not connected or queued for broadcast.")

async def job_poll_sheet_changes():
    """Polls the 'Changes' sheet every 5 minutes to detect newly published routine changes."""
    print("🔄 [Scheduler] Checking Master Google Sheet for routine changes...")
    try:
        new_changes = sheet_sync.check_new_changes()
        if new_changes:
            alert_msg = sheet_sync.format_changes_announcement(new_changes)
            print(f"🚨 Detected {len(new_changes)} new changes in Google Sheet!")

            # Record each change in database
            for c in new_changes:
                record_announced_change(
                    change_hash=c.change_hash,
                    date_str=c.date,
                    issue=c.issue,
                    course=c.course,
                    faculty=c.faculty,
                    prev_day=c.previous_day
                )

            save_announcement(
                title=f"Routine Changes ({len(new_changes)} issues)",
                content=alert_msg,
                source="sheet_change",
                target_group=settings.WHATSAPP_NOTICE_GROUP_ID,
                status="broadcasted"
            )

            # Broadcast to WhatsApp Notice Group
            await whatsapp_client.send_group_message(
                group_id=settings.WHATSAPP_NOTICE_GROUP_ID,
                message=alert_msg
            )
    except Exception as e:
        print(f"Error checking routine changes: {e}")

def schedule_makeup_class(course_code: str, faculty_name: str, date_str: str, time_str: str, room: str, announce_time: datetime):
    """Schedules a future makeup class announcement at a specific datetime."""
    notice = (
        f"📢 *MAKE-UP CLASS ANNOUNCEMENT*\n"
        f"🏛 *{settings.UNIVERSITY_NAME} {settings.DEPARTMENT_NAME} {settings.BATCH_NAME} Batch (Section {settings.SECTION_NAME})*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 *Course:* {course_code}\n"
        f"👤 *Faculty:* {faculty_name}\n"
        f"🗓 *Date:* {date_str}\n"
        f"⏰ *Time:* {time_str}\n"
        f"📍 *Room:* {room}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ *Attendance is mandatory. Please be present on time.*\n"
        f"— {settings.ADMIN_NAME} (CR Assistant Bot)"
    )

    async def _send_makeup():
        save_announcement(
            title=f"Makeup Class: {course_code}",
            content=notice,
            source="makeup_class",
            target_group=settings.WHATSAPP_NOTICE_GROUP_ID,
            status="broadcasted"
        )
        await whatsapp_client.send_group_message(
            group_id=settings.WHATSAPP_NOTICE_GROUP_ID,
            message=notice
        )

    scheduler.add_job(_send_makeup, "date", run_date=announce_time)
    print(f"✅ Scheduled makeup class for {course_code} at {announce_time}.")

def start_scheduler():
    # 1. 6:00 AM Sharp Daily Routine
    scheduler.add_job(
        job_daily_6am_routine,
        CronTrigger(hour=settings.DAILY_ROUTINE_HOUR, minute=settings.DAILY_ROUTINE_MINUTE),
        id="daily_6am_routine",
        replace_existing=True
    )

    # 2. Sheet Changes Poller (default every 5 mins / 300 secs)
    scheduler.add_job(
        job_poll_sheet_changes,
        IntervalTrigger(seconds=settings.SHEET_POLL_INTERVAL_SECONDS),
        id="poll_sheet_changes",
        replace_existing=True
    )

    scheduler.start()
    print(f"🚀 [Scheduler] Started: 6:00 AM Routine & Sheet Poller (every {settings.SHEET_POLL_INTERVAL_SECONDS}s) active.")
