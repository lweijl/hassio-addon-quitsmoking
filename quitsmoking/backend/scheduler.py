"""Notification scheduler — background task that sends context-aware notifications."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from .engine import ScheduleMode, TZ
from .notifications import send_notification, Actions
from .state import _get_engine, _entries_today, config_store, entry_store

logger = logging.getLogger(__name__)

_last_notification_check: Optional[datetime] = None

# Track which notifications have been sent today/this cycle to avoid duplicates
# Persisted to disk so restarts don't re-fire notifications
_SENT_FILE = None  # Initialized after DATA_DIR is available


def _get_sent_file():
    """Get the path to the sent-notifications file."""
    global _SENT_FILE
    if _SENT_FILE is None:
        from .persistence import DATA_DIR
        _SENT_FILE = DATA_DIR / "sent_notifications.json"
    return _SENT_FILE


def _load_sent() -> set[str]:
    """Load sent notifications from disk."""
    path = _get_sent_file()
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data) if isinstance(data, list) else set()
    except (json.JSONDecodeError, ValueError):
        return set()


def _save_sent(sent: set[str]) -> None:
    """Persist sent notifications to disk."""
    path = _get_sent_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(list(sent)), encoding="utf-8")


def _sent_key(tag: str, now: datetime) -> str:
    """Create a dedup key for a notification."""
    return f"{tag}:{now.date().isoformat()}"


def _was_sent(tag: str, now: datetime) -> bool:
    """Check if this notification was already sent today."""
    sent = _load_sent()
    return _sent_key(tag, now) in sent


def _mark_sent(tag: str, now: datetime) -> None:
    """Mark a notification as sent for today. Persists to disk."""
    sent = _load_sent()
    sent.add(_sent_key(tag, now))
    # Clean up old keys (anything not from today)
    today = now.date().isoformat()
    stale = {k for k in sent if not k.endswith(today)}
    sent.difference_update(stale)
    _save_sent(sent)


async def _notification_scheduler() -> None:
    """Background task that checks every 60 seconds if notifications should be sent."""
    global _last_notification_check
    while True:
        try:
            await _check_and_send_notifications()
            _last_notification_check = datetime.now(TZ)
        except Exception as exc:
            logger.error("Notification scheduler error: %s", exc)
        await asyncio.sleep(60)


async def _check_and_send_notifications() -> None:
    """Core notification logic — context-aware and respects smoking window.

    Rules:
    - No notifications outside the smoking window (quiet hours)
    - All notifications reflect current state (smoked today, remaining, etc.)
    - Interval mode: aware of next_allowed vs. window boundaries
    - Notifications held during quiet hours fire at window start
    """
    now = datetime.now(TZ)

    engine = _get_engine()
    config = config_store.load()
    entries = entry_store.load()
    schedule = engine.current_week_schedule(now)

    # Smoking window = notification window
    window_start_minutes = config.smoking_window_start_minutes
    window_end_minutes = config.smoking_window_end_minutes
    now_minutes = now.hour * 60 + now.minute

    # Don't send any notifications outside the smoking window
    if now_minutes < window_start_minutes or now_minutes > window_end_minutes:
        return

    # Compute current state (used by all notifications)
    today_entries = _entries_today(entries, now)
    smoked_today = len([e for e in today_entries if not e.is_bonus])
    allowance = engine.daily_allowance(now)
    remaining = max(0, allowance - smoked_today)
    non_bonus = [e for e in entries if not e.is_bonus]
    last_entry_ts = non_bonus[-1].timestamp.astimezone(TZ) if non_bonus else None

    total_smoked = len(entries)
    avoided = engine.cigarettes_avoided(total_smoked, now)
    saved = engine.money_saved(total_smoked, now)

    # ─── Morning status update (at window start or 09:00, whichever is later) ───
    morning_hour = max(9, window_start_minutes // 60)
    if now.hour >= morning_hour and not _was_sent("daily_reminder", now):
        if schedule.mode == ScheduleMode.QUIT:
            await send_notification(
                "🎯 Stay strong!",
                "You're in quit mode. No cigarettes today — you've got this! "
                f"({avoided} avoided, €{saved:.2f} saved)",
                actions=[Actions.open_progress(), Actions.stay_strong()],
                tag="daily_reminder",
            )
        elif schedule.mode == ScheduleMode.INTERVAL:
            # Interval mode: tell them about their current interval status
            if last_entry_ts:
                hours_since = (now - last_entry_ts).total_seconds() / 3600
                interval_hours = schedule.interval_hours
                next_allowed = last_entry_ts + timedelta(hours=interval_hours)

                if now >= next_allowed:
                    await send_notification(
                        "☀️ Good morning!",
                        f"Your interval is up ({hours_since:.1f}h since last). "
                        f"You may smoke when ready. Today so far: {smoked_today}.",
                        actions=[Actions.log_cigarette(), Actions.open_app()],
                        tag="daily_reminder",
                    )
                else:
                    next_str = next_allowed.strftime("%H:%M")
                    await send_notification(
                        "☀️ Good morning!",
                        f"Next allowed at {next_str}. "
                        f"Last one was {hours_since:.1f}h ago. Stay patient! 💪",
                        actions=[Actions.open_app(), Actions.open_progress()],
                        tag="daily_reminder",
                    )
            else:
                await send_notification(
                    "☀️ Good morning!",
                    f"Interval mode: {schedule.interval_hours:.1f}h between cigarettes. "
                    f"You haven't smoked yet — your call when to start the clock.",
                    actions=[Actions.open_app()],
                    tag="daily_reminder",
                )
        elif smoked_today == 0:
            await send_notification(
                "☀️ Good morning!",
                f"Today's allowance: {allowance} cigarettes. Make them count!",
                actions=[Actions.open_app(), Actions.open_progress()],
                tag="daily_reminder",
            )
        elif remaining > 0:
            await send_notification(
                "☀️ Morning check-in",
                f"You've had {smoked_today} so far today. {remaining} remaining. "
                f"Keep it up! ({avoided} total avoided)",
                actions=[Actions.open_app(), Actions.open_progress()],
                tag="daily_reminder",
            )
        else:
            await send_notification(
                "☀️ Morning check-in",
                f"You've used today's full allowance of {allowance} already. "
                f"Stay strong for the rest of the day! 💪",
                actions=[Actions.open_progress(), Actions.stay_strong()],
                tag="daily_reminder",
            )
        _mark_sent("daily_reminder", now)

        # Monday weekly summary
        if now.weekday() == 0 and not _was_sent("weekly_summary", now):
            last_week_start = engine.current_week_start(now) - timedelta(weeks=1)
            last_week_end = engine.current_week_start(now)
            last_week_entries = [
                e for e in entries
                if last_week_start <= e.timestamp.astimezone(TZ) < last_week_end
            ]
            smoked_last_week = len(last_week_entries)
            await send_notification(
                "📊 Weekly Summary",
                f"Last week: {smoked_last_week} smoked. "
                f"Total avoided: {avoided}. Total saved: €{saved:.2f}.",
                actions=[Actions.open_progress()],
                tag="weekly_summary",
            )
            _mark_sent("weekly_summary", now)

    # ─── Mode-specific notifications ───
    if schedule.mode == ScheduleMode.DAILY:
        times = engine.smoking_schedule_times(now)

        for idx, (h, m) in enumerate(times):
            slot_time = now.replace(hour=h, minute=m, second=0, microsecond=0)
            slot_key = f"smoke_time_{idx}"

            # Skip slots already used
            if idx < smoked_today:
                if not _was_sent(slot_key, now):
                    _mark_sent(slot_key, now)
                continue

            # Trigger if we've passed the slot time
            if now >= slot_time and not _was_sent(slot_key, now):
                if remaining > 0:
                    time_str = f"{h:02d}:{m:02d}"
                    await send_notification(
                        "⏰ Scheduled smoke time",
                        f"Slot {idx + 1}/{len(times)} ({time_str}). "
                        f"{remaining} remaining today. "
                        f"({smoked_today} used so far)",
                        actions=[
                            Actions.log_cigarette(),
                            Actions.skip(),
                            Actions.open_app(),
                        ],
                        tag="smoke_time",
                    )
                _mark_sent(slot_key, now)
                break

    elif schedule.mode == ScheduleMode.INTERVAL:
        if non_bonus:
            last_entry = non_bonus[-1].timestamp.astimezone(TZ)
            interval_hours = schedule.interval_hours
            next_allowed = last_entry + timedelta(hours=interval_hours)

            interval_key = f"interval_elapsed:{last_entry.isoformat()}"

            # Only notify if interval elapsed AND we're within the smoking window
            if now >= next_allowed and not _was_sent(interval_key, now):
                hours_since = (now - last_entry).total_seconds() / 3600
                await send_notification(
                    "✅ Interval elapsed",
                    f"It's been {hours_since:.1f}h since your last cigarette "
                    f"(interval: {interval_hours:.1f}h). You may smoke now. "
                    f"Today: {smoked_today} smoked, {avoided} total avoided.",
                    actions=[
                        Actions.log_cigarette(),
                        Actions.skip(),
                        Actions.open_app(),
                    ],
                    tag="interval_elapsed",
                )
                _mark_sent(interval_key, now)

    # ─── Evening check-in (1 hour before window end) ───
    evening_minutes = window_end_minutes - 60  # 1h before window closes
    evening_hour = evening_minutes // 60
    evening_minute = evening_minutes % 60

    if now.hour >= evening_hour and now.minute >= evening_minute and not _was_sent("evening_checkin", now):
        if schedule.mode == ScheduleMode.QUIT:
            await send_notification(
                "🌙 Day complete!",
                f"Another smoke-free day! Total avoided: {avoided}. "
                f"€{saved:.2f} saved. You're crushing it!",
                actions=[Actions.open_progress()],
                tag="evening_checkin",
            )
        elif schedule.mode == ScheduleMode.INTERVAL:
            # Interval mode evening: summarize the day in interval terms
            if last_entry_ts and last_entry_ts.date() == now.date():
                hours_since = (now - last_entry_ts).total_seconds() / 3600
                # Will next allowed be after window end?
                next_allowed_time = last_entry_ts + timedelta(hours=schedule.interval_hours)
                window_end_today = now.replace(
                    hour=window_end_minutes // 60,
                    minute=window_end_minutes % 60,
                    second=0, microsecond=0,
                )
                if next_allowed_time > window_end_today:
                    window_start_tomorrow = (now + timedelta(days=1)).replace(
                        hour=window_start_minutes // 60,
                        minute=window_start_minutes % 60,
                        second=0, microsecond=0,
                    )
                    next_str = window_start_tomorrow.strftime("%H:%M")
                    await send_notification(
                        "🌙 Done for today",
                        f"Today: {smoked_today} cigarettes. Last one {hours_since:.1f}h ago. "
                        f"Next allowed tomorrow at {next_str}. Good night! 🌙",
                        actions=[Actions.open_progress()],
                        tag="evening_checkin",
                    )
                else:
                    next_str = next_allowed_time.strftime("%H:%M")
                    await send_notification(
                        "🌙 Evening check-in",
                        f"Today: {smoked_today} cigarettes. "
                        f"Next allowed at {next_str} (still within window).",
                        actions=[Actions.open_app(), Actions.open_progress()],
                        tag="evening_checkin",
                    )
            elif smoked_today == 0:
                await send_notification(
                    "🌙 Incredible day!",
                    f"Zero cigarettes today in interval mode — amazing willpower! "
                    f"Total avoided: {avoided}.",
                    actions=[Actions.open_progress()],
                    tag="evening_checkin",
                )
            else:
                await send_notification(
                    "🌙 Day summary",
                    f"Today: {smoked_today} cigarettes. "
                    f"Total avoided: {avoided}. €{saved:.2f} saved.",
                    actions=[Actions.open_progress()],
                    tag="evening_checkin",
                )
        else:
            # Daily mode evening
            under_budget = allowance - smoked_today
            if under_budget > 0:
                await send_notification(
                    "🌙 Great day!",
                    f"You're {under_budget} under your daily limit ({smoked_today}/{allowance}). "
                    f"That's {under_budget} extra cigarettes avoided! 🎉",
                    actions=[Actions.open_progress()],
                    tag="evening_checkin",
                )
            elif under_budget == 0:
                await send_notification(
                    "🌙 Day complete",
                    f"Used your full allowance of {allowance} today. "
                    f"On track with your taper plan. 👍 ({avoided} total avoided)",
                    actions=[Actions.open_app()],
                    tag="evening_checkin",
                )
            else:
                over = abs(under_budget)
                await send_notification(
                    "🌙 Tough day",
                    f"Went {over} over today's limit ({smoked_today}/{allowance}). "
                    f"Tomorrow's a fresh start. You've still avoided {avoided} total.",
                    actions=[Actions.open_progress()],
                    tag="evening_checkin",
                )
        _mark_sent("evening_checkin", now)
