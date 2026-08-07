"""Debug routes: health_check, debug_status, test_notification, trigger_notification_check."""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from fastapi import APIRouter

from ..engine import ScheduleMode, TZ
from ..notifications import send_notification, Actions, get_notify_services
from ..persistence_db import DATA_DIR, DB_PATH
from ..state import _get_engine, _now, _entries_today, config_store, entry_store
from ..scheduler import _check_and_send_notifications, _last_notification_check

router = APIRouter()

INGRESS_PATH = os.environ.get("INGRESS_PATH", "")


@router.get("/api/health")
async def health_check():
    """Health check and debug info."""
    return {
        "status": "ok",
        "data_dir": str(DATA_DIR),
        "data_dir_exists": DATA_DIR.exists(),
        "db_path": str(DB_PATH),
        "db_exists": DB_PATH.exists(),
        "ingress_path": INGRESS_PATH,
        "cwd": os.getcwd(),
    }


@router.get("/api/debug")
async def debug_status():
    """Raw computed values for troubleshooting."""
    engine = await _get_engine()
    config = await config_store.load()
    entries = await entry_store.load()
    now = _now()
    schedule = engine.current_week_schedule(now)

    non_bonus = [e for e in entries if not e.is_bonus]
    last_entry_ts = non_bonus[-1].timestamp.astimezone(TZ) if non_bonus else None

    return {
        "now": now.isoformat(),
        "start_date": config.start_date.isoformat(),
        "quit_date": engine.quit_date().isoformat(),
        "days_since_start": engine.days_since_start(now),
        "days_until_quit": engine.days_until_quit(now),
        "week_index": engine.current_week_index(now),
        "total_weeks": len(config.weekly_schedules),
        "current_mode": schedule.mode.name,
        "interval_hours": schedule.interval_hours if schedule.mode == ScheduleMode.INTERVAL else None,
        "daily_allowance": engine.daily_allowance(now),
        "last_entry_ts": last_entry_ts.isoformat() if last_entry_ts else None,
        "can_smoke_now": engine.can_smoke_now(last_entry_ts, now),
        "next_allowed_time": (
            engine.next_allowed_time(last_entry_ts, now).isoformat()
            if engine.next_allowed_time(last_entry_ts, now)
            else None
        ),
        "time_until_next_seconds": engine.time_until_next(last_entry_ts, now),
        "total_entries": len(entries),
        "total_non_bonus": len(non_bonus),
        "entries_today": len(_entries_today(entries, now)),
        "notify_services": os.environ.get("NOTIFY_SERVICES", ""),
        "notify_service_legacy": os.environ.get("NOTIFY_SERVICE", ""),
        "notify_services_active": await get_notify_services(),
    }


@router.post("/api/notifications/schedule")
async def trigger_notification_check():
    """Manually trigger a notification check (can be called by HA automation)."""
    await _check_and_send_notifications()
    return {"status": "ok", "checked_at": datetime.now(TZ).isoformat()}


@router.get("/api/notifications/pending")
async def get_pending_notifications():
    """Return what notifications would be sent right now (dry-run)."""
    now = datetime.now(TZ)
    engine = await _get_engine()
    entries = await entry_store.load()
    schedule = engine.current_week_schedule(now)

    pending = []

    # 9:00 AM check
    if now.hour == 9 and now.minute == 0:
        allowance = engine.daily_allowance(now)
        if schedule.mode == ScheduleMode.QUIT:
            pending.append({
                "type": "daily_reminder",
                "title": "🎯 Stay strong!",
                "message": "You're in quit mode. No cigarettes today — you've got this!",
            })
        else:
            pending.append({
                "type": "daily_reminder",
                "title": "☀️ Good morning!",
                "message": f"Today's allowance: {allowance} cigarettes. Make them count!",
            })

        # Monday weekly summary
        if now.weekday() == 0:
            last_week_start = engine.current_week_start(now) - timedelta(weeks=1)
            last_week_end = engine.current_week_start(now)
            last_week_entries = [
                e for e in entries
                if last_week_start <= e.timestamp.astimezone(TZ) < last_week_end
            ]
            smoked_last_week = len(last_week_entries)
            total_smoked = len(entries)
            avoided = engine.cigarettes_avoided(total_smoked, now)
            saved = engine.money_saved(total_smoked, now)
            pending.append({
                "type": "weekly_summary",
                "title": "📊 Weekly Summary",
                "message": (
                    f"Last week: {smoked_last_week} smoked. "
                    f"Total avoided: {avoided}. Total saved: €{saved:.2f}."
                ),
            })

    # Mode-specific
    if schedule.mode == ScheduleMode.DAILY:
        times = engine.smoking_schedule_times(now)
        for h, m in times:
            if now.hour == h and now.minute == m:
                today_entries = _entries_today(entries, now)
                smoked = len([e for e in today_entries if not e.is_bonus])
                remaining = max(0, engine.daily_allowance(now) - smoked)
                if remaining > 0:
                    pending.append({
                        "type": "schedule_reminder",
                        "title": "⏰ Scheduled smoke time",
                        "message": f"You may have a cigarette now. {remaining} remaining today.",
                    })
                break

    elif schedule.mode == ScheduleMode.INTERVAL:
        non_bonus = [e for e in entries if not e.is_bonus]
        if non_bonus:
            last_entry = non_bonus[-1].timestamp.astimezone(TZ)
            interval_hours = schedule.interval_hours
            next_allowed = last_entry + timedelta(hours=interval_hours)
            current_minute = now.replace(second=0, microsecond=0)
            if current_minute == next_allowed.replace(second=0, microsecond=0):
                pending.append({
                    "type": "interval_elapsed",
                    "title": "✅ Interval elapsed",
                    "message": f"Your {interval_hours:.1f}h interval is up. You may smoke now.",
                })

    return {
        "pending": pending,
        "checked_at": now.isoformat(),
        "mode": schedule.mode.name.lower(),
        "last_scheduler_run": _last_notification_check.isoformat() if _last_notification_check else None,
    }


@router.post("/api/notifications/test")
async def test_notification():
    """Send a test notification with action buttons to verify navigation works."""
    from ..notifications import _addon_uri
    actions = [
        {"action": "URI", "title": "📱 Open App", "uri": _addon_uri("")},
        {"action": "QS_TEST", "title": "🧪 Test Event (no log)"},
        Actions.stay_strong(),
    ]
    result = await send_notification(
        "🧪 Test Notification",
        "Tap the buttons below to test navigation. Nothing will be logged.",
        actions=actions,
        tag="test",
    )

    # Return the exact payload we would send (for debugging)
    debug_payload = {
        "title": "🧪 Test Notification",
        "message": "Tap the buttons below to test navigation. Nothing will be logged.",
        "data": {
            "actions": actions,
            "tag": "test",
        },
    }

    services = await get_notify_services()

    return {
        "status": "ok" if result else "failed",
        "services": services,
        "uri_format": _addon_uri(""),
        "payload_sent": debug_payload,
        "sent_at": datetime.now(TZ).isoformat(),
    }
