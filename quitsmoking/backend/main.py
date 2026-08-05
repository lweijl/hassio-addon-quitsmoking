"""FastAPI application for QuitSmoking Home Assistant add-on."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta
from typing import Optional
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from zoneinfo import ZoneInfo

from .engine import ScheduleEngine, ScheduleConfig, ScheduleMode, TZ, WeekSchedule
from .models import (
    CigaretteEntry,
    ConfigUpdate,
    HistoryEntry,
    LogRequest,
    StatusResponse,
)
from .notifications import send_notification, Actions
from .persistence import ConfigStore, EntryStore

logger = logging.getLogger(__name__)

INGRESS_PATH = os.environ.get("INGRESS_PATH", "")


# ---------------------------------------------------------------------------
# Background scheduler
# ---------------------------------------------------------------------------

_scheduler_task: Optional[asyncio.Task] = None
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


async def _notification_scheduler():
    """Background task that checks every 60 seconds if notifications should be sent."""
    global _last_notification_check
    while True:
        try:
            await _check_and_send_notifications()
            _last_notification_check = datetime.now(TZ)
        except Exception as exc:
            logger.error("Notification scheduler error: %s", exc)
        await asyncio.sleep(60)


async def _check_and_send_notifications():
    """Core notification logic — checks conditions and sends (with dedup)."""
    now = datetime.now(TZ)

    engine = _get_engine()
    entries = entry_store.load()
    schedule = engine.current_week_schedule(now)

    # ─── 09:00 Good morning / daily reminder ───
    if now.hour >= 9 and not _was_sent("daily_reminder", now):
        allowance = engine.daily_allowance(now)
        if schedule.mode == ScheduleMode.QUIT:
            await send_notification(
                "🎯 Stay strong!",
                "You're in quit mode. No cigarettes today — you've got this!",
                actions=[Actions.open_progress(), Actions.stay_strong()],
                tag="daily_reminder",
            )
        else:
            await send_notification(
                "☀️ Good morning!",
                f"Today's allowance: {allowance} cigarettes. Make them count!",
                actions=[Actions.open_app(), Actions.open_progress()],
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
            total_smoked = len(entries)
            avoided = engine.cigarettes_avoided(total_smoked, now)
            saved = engine.money_saved(total_smoked, now)
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
        # Send reminders at scheduled smoking times
        times = engine.smoking_schedule_times(now)
        today_entries = _entries_today(entries, now)
        smoked = len([e for e in today_entries if not e.is_bonus])
        remaining = max(0, engine.daily_allowance(now) - smoked)

        for idx, (h, m) in enumerate(times):
            slot_time = now.replace(hour=h, minute=m, second=0, microsecond=0)
            slot_key = f"smoke_time_{idx}"
            # Trigger if we've passed the slot time and haven't sent yet
            if now >= slot_time and not _was_sent(slot_key, now):
                if remaining > 0:
                    await send_notification(
                        "⏰ Scheduled smoke time",
                        f"You may have a cigarette now. {remaining} remaining today.",
                        actions=[
                            Actions.log_cigarette(),
                            Actions.skip(),
                            Actions.open_app(),
                        ],
                        tag="smoke_time",
                    )
                _mark_sent(slot_key, now)
                break  # Only send for one slot at a time

    elif schedule.mode == ScheduleMode.INTERVAL:
        # Send alert when interval has elapsed
        non_bonus = [e for e in entries if not e.is_bonus]
        if non_bonus:
            last_entry = non_bonus[-1].timestamp.astimezone(TZ)
            interval_hours = schedule.interval_hours
            next_allowed = last_entry + timedelta(hours=interval_hours)

            # Use a key tied to the specific last_entry so it resets after each log
            interval_key = f"interval_elapsed:{last_entry.isoformat()}"

            # Trigger if interval has elapsed and we haven't notified for this entry yet
            if now >= next_allowed and not _was_sent(interval_key, now):
                await send_notification(
                    "✅ Interval elapsed",
                    f"Your {interval_hours:.1f}h interval is up. You may smoke now.",
                    actions=[
                        Actions.log_cigarette(),
                        Actions.skip(),
                        Actions.open_app(),
                    ],
                    tag="interval_elapsed",
                )
                _mark_sent(interval_key, now)

    # ─── 21:00 Evening check-in ───
    if now.hour >= 21 and not _was_sent("evening_checkin", now):
        today_entries = _entries_today(entries, now)
        smoked = len([e for e in today_entries if not e.is_bonus])
        allowance = engine.daily_allowance(now)
        under_budget = allowance - smoked

        if schedule.mode == ScheduleMode.QUIT:
            total_smoked = len(entries)
            avoided = engine.cigarettes_avoided(total_smoked, now)
            await send_notification(
                "🌙 Day complete!",
                f"Another smoke-free day! Total avoided: {avoided}. You're crushing it!",
                actions=[Actions.open_progress()],
                tag="evening_checkin",
            )
        elif under_budget > 0:
            await send_notification(
                "🌙 Great day!",
                f"You're {under_budget} under your daily limit. "
                f"That's {under_budget} extra cigarettes avoided! 🎉",
                actions=[Actions.open_progress()],
                tag="evening_checkin",
            )
        else:
            await send_notification(
                "🌙 Day complete",
                f"Used your full allowance of {allowance} today. "
                f"On track with your taper plan. 👍",
                actions=[Actions.open_app()],
                tag="evening_checkin",
            )
        _mark_sent("evening_checkin", now)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background scheduler on app startup."""
    global _scheduler_task
    _scheduler_task = asyncio.create_task(_notification_scheduler())
    yield
    if _scheduler_task:
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="QuitSmoking", root_path=INGRESS_PATH, lifespan=lifespan)

# Stores (singleton-like)
entry_store = EntryStore()
config_store = ConfigStore()


@app.get("/api/health")
async def health():
    """Health check and debug info."""
    from .persistence import DATA_DIR
    return {
        "status": "ok",
        "data_dir": str(DATA_DIR),
        "data_dir_exists": DATA_DIR.exists(),
        "entries_file": str(entry_store.path),
        "entries_file_exists": entry_store.path.exists(),
        "config_file": str(config_store.path),
        "config_file_exists": config_store.path.exists(),
        "ingress_path": INGRESS_PATH,
        "cwd": os.getcwd(),
    }


def _get_engine() -> ScheduleEngine:
    config = config_store.load()
    return ScheduleEngine(config)


def _now() -> datetime:
    return datetime.now(TZ)


def _entries_today(entries: list[CigaretteEntry], now: datetime) -> list[CigaretteEntry]:
    today = now.date()
    return [e for e in entries if e.timestamp.astimezone(TZ).date() == today]


def _entries_this_week(
    entries: list[CigaretteEntry], engine: ScheduleEngine, now: datetime
) -> list[CigaretteEntry]:
    week_start = engine.current_week_start(now)
    return [e for e in entries if e.timestamp.astimezone(TZ) >= week_start]


def _build_status(engine: ScheduleEngine, entries: list[CigaretteEntry]) -> StatusResponse:
    now = _now()
    schedule = engine.current_week_schedule(now)

    today_entries = _entries_today(entries, now)
    week_entries = _entries_this_week(entries, engine, now)

    smoked_today = len([e for e in today_entries if not e.is_bonus])
    bonus_used_this_week = len([e for e in week_entries if e.is_bonus])

    daily_allow = engine.daily_allowance(now)
    bonus_allow = engine.bonus_allowance(now)

    remaining_today = max(0, daily_allow - smoked_today)
    remaining_bonus = max(0, bonus_allow - bonus_used_this_week)

    # Last non-bonus entry for interval calculation
    non_bonus_entries = [e for e in entries if not e.is_bonus]
    last_entry_ts = non_bonus_entries[-1].timestamp.astimezone(TZ) if non_bonus_entries else None

    can_smoke = engine.can_smoke_now(last_entry_ts, now)
    time_until = engine.time_until_next(last_entry_ts, now)
    next_allowed = engine.next_allowed_time(last_entry_ts, now)

    # In daily mode, compute next_allowed_time from schedule times
    if schedule.mode == ScheduleMode.DAILY and remaining_today > 0:
        schedule_times = engine.smoking_schedule_times(now)
        if schedule_times:
            # Find the next scheduled time that hasn't been used yet
            # The number smoked tells us which slot we're on
            next_slot_idx = smoked_today  # 0-indexed: if smoked 2, next is slot 2

            # Scan forward from next_slot_idx to find the first FUTURE slot
            found_future = False
            for idx in range(next_slot_idx, len(schedule_times)):
                h, m = schedule_times[idx]
                next_scheduled = now.replace(hour=h, minute=m, second=0, microsecond=0)
                if next_scheduled > now:
                    next_allowed = next_scheduled
                    time_until = (next_scheduled - now).total_seconds()
                    can_smoke = False
                    found_future = True
                    break

            if not found_future:
                # All remaining slots have passed — can smoke now
                can_smoke = True
                time_until = 0.0
                next_allowed = None

    # Mode string
    if schedule.mode == ScheduleMode.DAILY:
        mode_str = "daily"
    elif schedule.mode == ScheduleMode.INTERVAL:
        mode_str = "interval"
    else:
        mode_str = "quit"

    total_smoked = len(entries)

    return StatusResponse(
        week_index=engine.current_week_index(now),
        week_start=engine.current_week_start(now),
        mode=mode_str,
        daily_allowance=daily_allow,
        bonus_allowance=bonus_allow,
        interval_hours=engine.current_interval(now),
        smoked_today=smoked_today,
        bonus_used_this_week=bonus_used_this_week,
        remaining_today=remaining_today,
        remaining_bonus=remaining_bonus,
        can_smoke=can_smoke,
        time_until_next_seconds=time_until,
        next_allowed_time=next_allowed,
        schedule_times=engine.smoking_schedule_times(now),
        days_since_start=engine.days_since_start(now),
        days_until_quit=engine.days_until_quit(now),
        quit_date=engine.quit_date(),
        total_smoked=total_smoked,
        cigarettes_avoided=engine.cigarettes_avoided(total_smoked, now),
        money_saved=engine.money_saved(total_smoked, now),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/status", response_model=StatusResponse)
async def get_status():
    engine = _get_engine()
    entries = entry_store.load()
    status = _build_status(engine, entries)
    return JSONResponse(
        content=status.model_dump(mode="json"),
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.post("/api/log", response_model=StatusResponse)
async def log_cigarette(req: LogRequest):
    engine = _get_engine()
    now = _now()

    # Allow logging for a past date/time
    entry_time = req.timestamp.astimezone(TZ) if req.timestamp else now

    entry = CigaretteEntry(
        id=uuid4(),
        timestamp=entry_time,
        is_bonus=req.is_bonus,
    )
    entry_store.add_entry(entry)

    # Re-sort entries by timestamp (in case backfilling)
    entries = entry_store.load()
    entries.sort(key=lambda e: e.timestamp)
    entry_store.save(entries)

    status = _build_status(engine, entries)

    # Send notification
    if req.is_bonus:
        await send_notification(
            "🎁 Bonus used",
            f"Bonus cigarette logged. {status.remaining_bonus} bonus remaining this week.",
            actions=[Actions.open_app()],
            tag="logged",
        )
    else:
        if status.remaining_today == 0:
            avoided = status.cigarettes_avoided
            saved = status.money_saved
            await send_notification(
                "⚠️ Daily limit reached",
                f"All regular cigarettes used for today. "
                f"You've avoided {avoided} total (€{saved:.2f} saved).",
                actions=[
                    Actions.log_bonus() if status.remaining_bonus > 0 else Actions.stay_strong(),
                    Actions.open_progress(),
                ],
                tag="limit_reached",
            )
        else:
            # Build a useful message with next-time info
            parts = [f"{status.remaining_today} remaining today."]
            if status.next_allowed_time and status.time_until_next_seconds > 0:
                next_str = status.next_allowed_time.astimezone(TZ).strftime("%H:%M")
                parts.append(f"Next at {next_str}.")
            if status.cigarettes_avoided > 0:
                parts.append(f"📊 {status.cigarettes_avoided} avoided so far!")
            await send_notification(
                "🚬 Logged",
                " ".join(parts),
                actions=[Actions.open_app()],
                tag="logged",
            )

    return status


@app.post("/api/undo", response_model=StatusResponse)
async def undo_last():
    entries = entry_store.load()
    if not entries:
        raise HTTPException(status_code=404, detail="No entries to undo")

    last = entries[-1]
    now = _now()
    age = (now - last.timestamp.astimezone(TZ)).total_seconds()
    if age > 300:
        raise HTTPException(
            status_code=400,
            detail="Can only undo entries within 5 minutes",
        )

    entry_store.remove_last()
    engine = _get_engine()
    entries = entry_store.load()
    return _build_status(engine, entries)


@app.get("/api/history")
async def get_history():
    """Return daily aggregated history for the chart.

    Returns: {"days": [{"date": "2026-06-15", "count": 8, "bonus_count": 0, "allowance": 8}, ...]}
    """
    engine = _get_engine()
    entries = entry_store.load()

    if not entries:
        return {"days": []}

    # Aggregate entries by date
    daily: dict[str, dict] = defaultdict(lambda: {"count": 0, "bonus_count": 0})

    for e in entries:
        ts = e.timestamp.astimezone(TZ) if e.timestamp.tzinfo else e.timestamp.replace(tzinfo=TZ)
        day_key = ts.date().isoformat()
        daily[day_key]["count"] += 1
        if e.is_bonus:
            daily[day_key]["bonus_count"] += 1

    # Build day-by-day from start to today
    config = config_store.load()
    start = config.start_date
    today = _now().date()
    days_list = []

    current = start
    while current <= today:
        day_key = current.isoformat()
        day_data = daily.get(day_key, {"count": 0, "bonus_count": 0})

        # Calculate allowance for this day
        day_dt = datetime.combine(current, datetime.min.time(), tzinfo=TZ)
        allowance = engine.daily_allowance(day_dt)

        days_list.append({
            "date": day_key,
            "count": day_data["count"],
            "bonus_count": day_data["bonus_count"],
            "allowance": allowance,
        })
        current += timedelta(days=1)

    return {"days": days_list}


@app.get("/api/history/entries", response_model=list[HistoryEntry])
async def get_history_entries():
    """Return raw entry list (for debugging/export)."""
    engine = _get_engine()
    entries = entry_store.load()
    result = []
    for e in entries:
        ts_aware = e.timestamp.astimezone(TZ) if e.timestamp.tzinfo else e.timestamp.replace(tzinfo=TZ)
        week_idx = engine.current_week_index(ts_aware)
        result.append(
            HistoryEntry(
                id=e.id,
                timestamp=e.timestamp,
                is_bonus=e.is_bonus,
                week_index=week_idx,
            )
        )
    return result


@app.get("/api/config")
async def get_config():
    config = config_store.load()
    schedules = []
    for s in config.weekly_schedules:
        if s.mode == ScheduleMode.DAILY:
            schedules.append({"mode": "daily", "allowance": s.allowance})
        elif s.mode == ScheduleMode.INTERVAL:
            schedules.append({"mode": "interval", "interval_hours": s.interval_hours})
        else:
            schedules.append({"mode": "quit"})

    return {
        "start_date": config.start_date.isoformat(),
        "weekly_schedules": schedules,
        "bonus_per_week": config.bonus_per_week,
        "cost_per_cigarette": config.cost_per_cigarette,
        "baseline_daily_count": config.baseline_daily_count,
        "smoking_window_start_minutes": config.smoking_window_start_minutes,
        "smoking_window_end_minutes": config.smoking_window_end_minutes,
    }


@app.put("/api/config")
async def update_config(update: ConfigUpdate):
    config = config_store.load()

    if update.start_date is not None:
        config.start_date = update.start_date
    if update.bonus_per_week is not None:
        config.bonus_per_week = update.bonus_per_week
    if update.cost_per_cigarette is not None:
        config.cost_per_cigarette = update.cost_per_cigarette
    if update.baseline_daily_count is not None:
        config.baseline_daily_count = update.baseline_daily_count
    if update.smoking_window_start_minutes is not None:
        config.smoking_window_start_minutes = update.smoking_window_start_minutes
    if update.smoking_window_end_minutes is not None:
        config.smoking_window_end_minutes = update.smoking_window_end_minutes
    if update.weekly_schedules is not None:
        new_schedules = []
        for s in update.weekly_schedules:
            if s.mode == "daily":
                new_schedules.append(WeekSchedule.daily(s.allowance))
            elif s.mode == "interval":
                new_schedules.append(WeekSchedule.interval(s.interval_hours))
            else:
                new_schedules.append(WeekSchedule.quit())
        config.weekly_schedules = new_schedules

    config_store.save(config)
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Import (migrate from Swift app or restore backup)
# ---------------------------------------------------------------------------

class ImportEntriesRequest(BaseModel):
    """Accepts either the Swift app format or the HA addon format."""
    # Swift format: {"version": 1, "entries": [...]}
    version: Optional[int] = None
    entries: Optional[list[dict]] = None


@app.post("/api/import/entries")
async def import_entries(request: Request):
    """Import entries from the Swift macOS app or a previous export.

    Accepts:
      - Swift format: {"version": 1, "entries": [{"id": "...", "timestamp": "...", "isBonus": false}]}
      - HA addon format: [{"id": "...", "timestamp": "...", "is_bonus": false}]
    """
    body = await request.json()

    # Detect format
    if isinstance(body, list):
        # Already in HA addon format (flat array)
        raw_entries = body
    elif isinstance(body, dict) and "entries" in body:
        # Swift format with version wrapper
        raw_entries = body["entries"]
    else:
        raise HTTPException(status_code=400, detail="Unrecognized format. Expected array or {entries: [...]}.")

    # Parse entries, handling both camelCase (Swift) and snake_case (addon) keys
    imported = []
    for entry in raw_entries:
        entry_id = entry.get("id", str(uuid4()))
        timestamp = entry.get("timestamp")
        # Handle both isBonus (Swift) and is_bonus (addon)
        is_bonus = entry.get("is_bonus", entry.get("isBonus", False))

        if not timestamp:
            raise HTTPException(status_code=400, detail=f"Entry missing timestamp: {entry}")

        imported.append(CigaretteEntry(
            id=entry_id,
            timestamp=datetime.fromisoformat(timestamp.replace("Z", "+00:00")),
            is_bonus=is_bonus,
        ))

    # Merge with existing (deduplicate by ID)
    existing = entry_store.load()
    existing_ids = {str(e.id) for e in existing}
    new_entries = [e for e in imported if str(e.id) not in existing_ids]

    all_entries = existing + new_entries
    # Sort by timestamp
    all_entries.sort(key=lambda e: e.timestamp)
    entry_store.save(all_entries)

    return {
        "status": "ok",
        "imported": len(new_entries),
        "skipped_duplicates": len(imported) - len(new_entries),
        "total": len(all_entries),
    }


@app.post("/api/import/config")
async def import_config(request: Request):
    """Import config from the Swift macOS app or a previous export.

    Accepts both Swift format (camelCase) and HA addon format (snake_case).
    """
    body = await request.json()

    # Detect format by checking key style
    if "startDate" in body:
        # Swift format — convert
        schedules = []
        for s in body.get("weeklySchedules", []):
            mode = s["mode"]
            if mode == "daily":
                schedules.append(WeekSchedule.daily(s["allowance"]))
            elif mode == "interval":
                schedules.append(WeekSchedule.interval(s["hours"]))
            else:
                schedules.append(WeekSchedule.quit())

        window_start = 450
        window_end = 1350
        if "smokingWindowStart" in body:
            parts = body["smokingWindowStart"].split(":")
            window_start = int(parts[0]) * 60 + int(parts[1])
        if "smokingWindowEnd" in body:
            parts = body["smokingWindowEnd"].split(":")
            window_end = int(parts[0]) * 60 + int(parts[1])

        config = ScheduleConfig(
            start_date=date.fromisoformat(body["startDate"]),
            weekly_schedules=schedules,
            bonus_per_week=body.get("bonusPerWeek", 1),
            cost_per_cigarette=body.get("costPerCigarette", 0.565),
            baseline_daily_count=body.get("baselineDailyCount", 20),
            smoking_window_start_minutes=window_start,
            smoking_window_end_minutes=window_end,
        )
    elif "start_date" in body:
        # Already in HA addon format
        schedules = []
        for s in body.get("weekly_schedules", []):
            mode = s["mode"]
            if mode == "daily":
                schedules.append(WeekSchedule.daily(s["allowance"]))
            elif mode == "interval":
                schedules.append(WeekSchedule.interval(s["interval_hours"]))
            else:
                schedules.append(WeekSchedule.quit())

        config = ScheduleConfig(
            start_date=date.fromisoformat(body["start_date"]),
            weekly_schedules=schedules,
            bonus_per_week=body.get("bonus_per_week", 1),
            cost_per_cigarette=body.get("cost_per_cigarette", 0.565),
            baseline_daily_count=body.get("baseline_daily_count", 20),
            smoking_window_start_minutes=body.get("smoking_window_start_minutes", 450),
            smoking_window_end_minutes=body.get("smoking_window_end_minutes", 1350),
        )
    else:
        raise HTTPException(status_code=400, detail="Unrecognized config format.")

    config_store.save(config)
    return {
        "status": "ok",
        "start_date": config.start_date.isoformat(),
        "weeks": len(config.weekly_schedules),
    }


# ---------------------------------------------------------------------------
# Catch-Up Manager
# ---------------------------------------------------------------------------

class BackfillDay(BaseModel):
    date: str
    count: int
    is_bonus: bool = False


class BackfillRequest(BaseModel):
    days: list[BackfillDay]


@app.get("/api/catchup")
async def get_catchup():
    """Find missed days and partially-logged yesterday."""
    engine = _get_engine()
    config = config_store.load()
    entries = entry_store.load()
    now = _now()
    yesterday = now.date() - timedelta(days=1)

    # Build a map of entries per day
    daily_counts: dict[date, int] = defaultdict(int)
    for e in entries:
        ts = e.timestamp.astimezone(TZ) if e.timestamp.tzinfo else e.timestamp.replace(tzinfo=TZ)
        daily_counts[ts.date()] += 1

    # Find missed days (0 entries) from start_date to yesterday
    missed_days = []
    current = config.start_date
    while current <= yesterday:
        if daily_counts.get(current, 0) == 0:
            day_dt = datetime.combine(current, time.min, tzinfo=TZ)
            allowance = engine.daily_allowance(day_dt)
            if allowance > 0:  # Only include days where smoking was expected
                missed_days.append({
                    "date": current.isoformat(),
                    "allowance": allowance,
                })
        current += timedelta(days=1)

    # Check if yesterday was partially logged
    partial_yesterday = None
    yesterday_count = daily_counts.get(yesterday, 0)
    if yesterday_count > 0:
        yesterday_dt = datetime.combine(yesterday, time.min, tzinfo=TZ)
        yesterday_allowance = engine.daily_allowance(yesterday_dt)
        if yesterday_count < yesterday_allowance:
            partial_yesterday = {
                "date": yesterday.isoformat(),
                "logged": yesterday_count,
                "allowance": yesterday_allowance,
            }

    return {
        "missed_days": missed_days,
        "partial_yesterday": partial_yesterday,
    }


@app.post("/api/catchup/backfill")
async def backfill_days(req: BackfillRequest):
    """Backfill entries for missed days with evenly-spaced timestamps."""
    config = config_store.load()
    entries = entry_store.load()

    window_start_minutes = config.smoking_window_start_minutes
    window_end_minutes = config.smoking_window_end_minutes
    window_duration = window_end_minutes - window_start_minutes

    entries_added = 0

    for day_req in req.days:
        day_date = date.fromisoformat(day_req.date)

        count = day_req.count
        if count <= 0:
            continue

        # Create entries spread across the smoking window
        for i in range(count):
            if count == 1:
                total_minutes = window_start_minutes + window_duration // 2
            else:
                total_minutes = window_start_minutes + int(i * window_duration / (count - 1))

            hour = total_minutes // 60
            minute = total_minutes % 60

            ts = datetime.combine(
                day_date, time(hour=hour, minute=minute), tzinfo=TZ
            )

            entry = CigaretteEntry(
                id=uuid4(),
                timestamp=ts,
                is_bonus=day_req.is_bonus,
            )
            entries.append(entry)
            entries_added += 1

    # Sort by timestamp and save
    entries.sort(key=lambda e: e.timestamp)
    entry_store.save(entries)

    return {
        "status": "ok",
        "entries_added": entries_added,
        "total": len(entries),
    }


# ---------------------------------------------------------------------------
# Progress / Savings endpoint
# ---------------------------------------------------------------------------

FUN_EQUIVALENTS = [
    ("Coffee ☕", 3.50),
    ("Pizza 🍕", 12.0),
    ("Movie ticket 🎬", 14.0),
    ("Book 📚", 20.0),
    ("Concert ticket 🎵", 65.0),
    ("Weekend trip 🧳", 200.0),
    ("New phone 📱", 800.0),
]

MILESTONES_AVOIDED = [100, 250, 500, 1000, 2000, 5000]
MILESTONES_SAVED = [50, 100, 200, 500, 1000, 2000]


@app.get("/api/progress")
async def get_progress():
    """Return comprehensive progress/savings data for charting."""
    engine = _get_engine()
    config = config_store.load()
    entries = entry_store.load()
    now = _now()
    today = now.date()

    # --- Aggregate entries by date ---
    daily_counts: dict[date, int] = defaultdict(int)
    for e in entries:
        ts = e.timestamp.astimezone(TZ) if e.timestamp.tzinfo else e.timestamp.replace(tzinfo=TZ)
        daily_counts[ts.date()] += 1

    # --- Build cumulative arrays ---
    cumulative_avoided = []
    cumulative_saved = []
    total_smoked_so_far = 0
    baseline = config.baseline_daily_count
    cost = config.cost_per_cigarette

    current = config.start_date
    while current <= today:
        smoked_that_day = daily_counts.get(current, 0)
        total_smoked_so_far += smoked_that_day
        days_elapsed = (current - config.start_date).days + 1
        would_have_smoked = days_elapsed * baseline
        avoided = max(0, would_have_smoked - total_smoked_so_far)
        saved = avoided * cost

        cumulative_avoided.append({
            "date": current.isoformat(),
            "avoided_cumulative": avoided,
        })
        cumulative_saved.append({
            "date": current.isoformat(),
            "saved_cumulative": round(saved, 2),
        })
        current += timedelta(days=1)

    # --- Current totals ---
    total_smoked = len(entries)
    current_avoided = engine.cigarettes_avoided(total_smoked, now)
    current_saved = engine.money_saved(total_smoked, now)

    # --- Projections ---
    quit_dt = engine.quit_date()
    total_days_program = (quit_dt - config.start_date).days
    # Project assuming current avg smoking rate continues
    days_so_far = max(1, engine.days_since_start(now))
    avg_daily_smoked = total_smoked / days_so_far
    days_remaining = max(0, (quit_dt - today).days)
    projected_total_smoked = total_smoked + int(avg_daily_smoked * days_remaining)
    projected_would_have = total_days_program * baseline
    projected_total_avoided = max(0, projected_would_have - projected_total_smoked)
    projected_total_saved = round(projected_total_avoided * cost, 2)

    projections = {
        "quit_date": quit_dt.isoformat(),
        "projected_total_avoided": projected_total_avoided,
        "projected_total_saved": projected_total_saved,
    }

    # --- Milestones ---
    milestones = []

    # Avoided milestones
    for target in MILESTONES_AVOIDED:
        reached = current_avoided >= target
        reached_date = None
        if reached:
            # Find the date it was reached
            running_smoked = 0
            d = config.start_date
            while d <= today:
                running_smoked += daily_counts.get(d, 0)
                days_el = (d - config.start_date).days + 1
                would = days_el * baseline
                if would - running_smoked >= target:
                    reached_date = d.isoformat()
                    break
                d += timedelta(days=1)
        milestones.append({
            "name": f"{target} avoided",
            "reached": reached,
            "date": reached_date,
        })

    # Saved milestones
    for target in MILESTONES_SAVED:
        reached = current_saved >= target
        reached_date = None
        if reached:
            running_smoked = 0
            d = config.start_date
            while d <= today:
                running_smoked += daily_counts.get(d, 0)
                days_el = (d - config.start_date).days + 1
                would = days_el * baseline
                av = would - running_smoked
                if av * cost >= target:
                    reached_date = d.isoformat()
                    break
                d += timedelta(days=1)
        milestones.append({
            "name": f"€{target} saved",
            "reached": reached,
            "date": reached_date,
        })

    # --- Fun equivalents ---
    fun_equivalents = []
    for name, unit_cost in FUN_EQUIVALENTS:
        count = int(current_saved / unit_cost)
        if count > 0:
            fun_equivalents.append({
                "amount": round(current_saved, 2),
                "equivalent": f"That's {count} {name}",
            })

    # --- Weekly comparison ---
    weekly_comparison = []
    num_weeks = min(
        len(config.weekly_schedules),
        (today - config.start_date).days // 7 + 1,
    )
    for week_idx in range(num_weeks):
        week_start_date = config.start_date + timedelta(weeks=week_idx)
        week_end_date = week_start_date + timedelta(days=7)

        week_smoked = 0
        d = week_start_date
        while d < week_end_date and d <= today:
            week_smoked += daily_counts.get(d, 0)
            d += timedelta(days=1)

        # Allowance for the week
        week_dt = datetime.combine(week_start_date, time.min, tzinfo=TZ)
        daily_allow = engine.daily_allowance(week_dt)
        days_in_week = min(7, (today - week_start_date).days + 1) if week_end_date > today else 7
        week_allowance = daily_allow * days_in_week

        # Baseline for the week
        week_baseline = baseline * days_in_week
        saved_vs_baseline = (week_baseline - week_smoked) * cost

        weekly_comparison.append({
            "week": week_idx + 1,
            "smoked": week_smoked,
            "allowance": week_allowance,
            "saved_vs_baseline": round(saved_vs_baseline, 2),
        })

    return {
        "cumulative_avoided": cumulative_avoided,
        "cumulative_saved": cumulative_saved,
        "projections": projections,
        "milestones": milestones,
        "fun_equivalents": fun_equivalents,
        "weekly_comparison": weekly_comparison,
    }


# ---------------------------------------------------------------------------
# Notifications endpoints
# ---------------------------------------------------------------------------

@app.post("/api/notifications/schedule")
async def trigger_notification_check():
    """Manually trigger a notification check (can be called by HA automation)."""
    await _check_and_send_notifications()
    return {"status": "ok", "checked_at": datetime.now(TZ).isoformat()}


@app.get("/api/notifications/pending")
async def get_pending_notifications():
    """Return what notifications would be sent right now (dry-run)."""
    now = datetime.now(TZ)
    engine = _get_engine()
    entries = entry_store.load()
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


@app.post("/api/notifications/test")
async def test_notification():
    """Send a test notification to verify notification config is working."""
    from .notifications import NOTIFY_SERVICES
    result = await send_notification(
        "🧪 Test Notification",
        "If you see this, notifications are working! "
        f"Configured services: {', '.join(NOTIFY_SERVICES)}",
        actions=[Actions.open_app()],
        tag="test",
    )
    return {
        "status": "ok" if result else "failed",
        "services": NOTIFY_SERVICES,
        "sent_at": datetime.now(TZ).isoformat(),
    }


@app.get("/api/debug")
async def debug_status():
    """Raw computed values for troubleshooting."""
    engine = _get_engine()
    config = config_store.load()
    entries = entry_store.load()
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
        "notify_services": __import__("os").environ.get("NOTIFY_SERVICES", ""),
        "notify_service_legacy": __import__("os").environ.get("NOTIFY_SERVICE", ""),
    }


# ---------------------------------------------------------------------------
# Notification action endpoints (triggered by tapping notification buttons)
# ---------------------------------------------------------------------------

@app.get("/api/actions/log")
@app.post("/api/actions/log")
async def action_log_cigarette():
    """Quick-log from notification button. Logs a regular cigarette."""
    engine = _get_engine()
    now = _now()

    entry = CigaretteEntry(
        id=uuid4(),
        timestamp=now,
        is_bonus=False,
    )
    entry_store.add_entry(entry)

    entries = entry_store.load()
    status = _build_status(engine, entries)

    # Send a confirmation notification (replaces the action notification)
    parts = [f"✓ Logged. {status.remaining_today} remaining today."]
    if status.next_allowed_time and status.time_until_next_seconds > 0:
        next_str = status.next_allowed_time.astimezone(TZ).strftime("%H:%M")
        parts.append(f"Next at {next_str}.")
    await send_notification(
        "🚬 Logged from notification",
        " ".join(parts),
        tag="logged",
    )

    # Return HTML for when opened in browser via URI
    return JSONResponse(
        content={"status": "ok", "action": "logged", "remaining_today": status.remaining_today},
        headers={"Content-Type": "application/json"},
    )


@app.get("/api/actions/log_bonus")
@app.post("/api/actions/log_bonus")
async def action_log_bonus():
    """Quick-log bonus from notification button."""
    engine = _get_engine()
    now = _now()

    # Check if bonus is available
    entries = entry_store.load()
    week_entries = _entries_this_week(entries, engine, now)
    bonus_used = len([e for e in week_entries if e.is_bonus])
    bonus_allow = engine.bonus_allowance(now)

    if bonus_used >= bonus_allow:
        await send_notification(
            "❌ No bonus left",
            "You've used all bonus cigarettes this week.",
            tag="logged",
        )
        return JSONResponse(
            content={"status": "error", "detail": "No bonus remaining"},
            status_code=400,
        )

    entry = CigaretteEntry(
        id=uuid4(),
        timestamp=now,
        is_bonus=True,
    )
    entry_store.add_entry(entry)

    remaining_bonus = bonus_allow - bonus_used - 1
    await send_notification(
        "🎁 Bonus logged",
        f"Bonus cigarette logged. {remaining_bonus} bonus remaining this week.",
        tag="logged",
    )

    return JSONResponse(
        content={"status": "ok", "action": "bonus_logged", "remaining_bonus": remaining_bonus},
    )


@app.get("/api/actions/skip")
@app.post("/api/actions/skip")
async def action_skip():
    """Record a successful craving skip. Sends encouragement."""
    engine = _get_engine()
    entries = entry_store.load()
    now = _now()
    total_smoked = len(entries)
    avoided = engine.cigarettes_avoided(total_smoked, now)
    saved = engine.money_saved(total_smoked, now)

    encouragements = [
        "You're stronger than the craving! 💪",
        "Every skip is a victory. Keep going! 🏆",
        "Your lungs just thanked you. 🫁",
        "Craving passed. Freedom gets easier! 🌅",
        "That's willpower in action! 🔥",
    ]
    from random import choice
    msg = choice(encouragements)

    await send_notification(
        "💪 Craving resisted!",
        f"{msg} You've avoided {avoided} cigarettes (€{saved:.2f} saved).",
        actions=[Actions.open_progress()],
        tag="encouragement",
    )

    return JSONResponse(
        content={"status": "ok", "action": "skipped", "encouragement": msg},
    )


# ---------------------------------------------------------------------------
# Health Timeline
# ---------------------------------------------------------------------------

HEALTH_MILESTONES = [
    {"minutes": 20, "title": "Heart rate normalizes", "icon": "❤️", "description": "Your heart rate and blood pressure begin to drop to normal levels."},
    {"minutes": 480, "title": "Oxygen levels normal", "icon": "🫁", "description": "Carbon monoxide in your blood drops to normal. Oxygen levels return to normal."},
    {"minutes": 1440, "title": "Heart attack risk drops", "icon": "💓", "description": "Your risk of heart attack begins to decrease."},
    {"minutes": 2880, "title": "Taste & smell improve", "icon": "👃", "description": "Nerve endings start to regrow. Your sense of taste and smell begin to improve."},
    {"minutes": 4320, "title": "Breathing easier", "icon": "🌬️", "description": "Bronchial tubes begin to relax and open up. Breathing becomes easier."},
    {"minutes": 14400, "title": "Circulation improves", "icon": "🏃", "description": "Your circulation improves significantly. Walking becomes easier. Lung function increases up to 30%."},
    {"minutes": 43200, "title": "Cough reduces", "icon": "😮‍💨", "description": "Cilia regrow in lungs. They can handle mucus, clean the lungs, and reduce infection risk. Coughing and shortness of breath decrease."},
    {"minutes": 131400, "title": "Lung function restored", "icon": "🫁✨", "description": "Lung function continues to improve. Energy levels increase significantly."},
    {"minutes": 525600, "title": "Heart disease risk halved", "icon": "❤️‍🩹", "description": "Your risk of coronary heart disease is half that of a smoker's."},
    {"minutes": 2628000, "title": "Stroke risk normalized", "icon": "🧠", "description": "Your risk of stroke is reduced to that of a non-smoker."},
    {"minutes": 5256000, "title": "Lung cancer risk halved", "icon": "🎗️", "description": "Your risk of lung cancer is about half that of a continuing smoker."},
]


@app.get("/api/health-timeline")
async def get_health_timeline():
    """Return health recovery milestones with progress based on time since last smoke."""
    entries = entry_store.load()
    now = _now()

    # Find the last cigarette (any, including bonus)
    if entries:
        last_smoke = entries[-1].timestamp.astimezone(TZ)
    else:
        # No entries at all — use start date as reference
        config = config_store.load()
        last_smoke = datetime.combine(config.start_date, datetime.min.time(), tzinfo=TZ)

    minutes_since_last = (now - last_smoke).total_seconds() / 60

    milestones = []
    for m in HEALTH_MILESTONES:
        reached = minutes_since_last >= m["minutes"]
        progress = min(1.0, minutes_since_last / m["minutes"]) if m["minutes"] > 0 else 1.0

        # Calculate when this milestone will be reached
        target_time = last_smoke + timedelta(minutes=m["minutes"])

        milestones.append({
            "title": m["title"],
            "icon": m["icon"],
            "description": m["description"],
            "minutes_required": m["minutes"],
            "reached": reached,
            "progress": round(progress, 4),
            "target_time": target_time.isoformat() if not reached else None,
            "reached_at": target_time.isoformat() if reached else None,
        })

    return {
        "last_smoke": last_smoke.isoformat(),
        "minutes_since_last": round(minutes_since_last, 1),
        "hours_since_last": round(minutes_since_last / 60, 1),
        "milestones": milestones,
    }


# ---------------------------------------------------------------------------
# Craving Journal
# ---------------------------------------------------------------------------

CRAVING_TRIGGERS = [
    "stress",
    "boredom",
    "social",
    "after_meal",
    "coffee",
    "alcohol",
    "habit",
    "anxiety",
    "celebration",
    "other",
]


class CravingEntry(BaseModel):
    trigger: str
    intensity: int = 3  # 1-5
    notes: Optional[str] = None
    resisted: bool = True


class CravingRecord(BaseModel):
    id: UUID
    timestamp: datetime
    trigger: str
    intensity: int
    notes: Optional[str]
    resisted: bool


class CravingStore:
    """Persist craving journal entries."""

    def __init__(self):
        from .persistence import DATA_DIR, _atomic_write
        self.path = DATA_DIR / "cravings.json"
        self._atomic_write = _atomic_write

    def load(self) -> list[CravingRecord]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return [CravingRecord(**r) for r in raw]
        except (json.JSONDecodeError, KeyError, ValueError):
            return []

    def save(self, records: list[CravingRecord]) -> None:
        data = [r.model_dump(mode="json") for r in records]
        self._atomic_write(self.path, json.dumps(data, indent=2, default=str))

    def add(self, record: CravingRecord) -> None:
        records = self.load()
        records.append(record)
        self.save(records)


craving_store = CravingStore()


@app.post("/api/cravings")
async def log_craving(entry: CravingEntry):
    """Log a craving event."""
    if entry.intensity < 1 or entry.intensity > 5:
        raise HTTPException(status_code=400, detail="Intensity must be 1-5")
    if entry.trigger not in CRAVING_TRIGGERS:
        raise HTTPException(status_code=400, detail=f"Invalid trigger. Valid: {CRAVING_TRIGGERS}")

    record = CravingRecord(
        id=uuid4(),
        timestamp=_now(),
        trigger=entry.trigger,
        intensity=entry.intensity,
        notes=entry.notes,
        resisted=entry.resisted,
    )
    craving_store.add(record)

    return {"status": "ok", "id": str(record.id), "timestamp": record.timestamp.isoformat()}


@app.get("/api/cravings")
async def get_cravings():
    """Return all craving entries."""
    records = craving_store.load()
    return {"cravings": [r.model_dump(mode="json") for r in records]}


@app.get("/api/cravings/patterns")
async def get_craving_patterns():
    """Analyze craving patterns: by trigger, by hour, by day of week, intensity trends."""
    records = craving_store.load()
    now = _now()

    if not records:
        return {
            "total_cravings": 0,
            "resisted_count": 0,
            "resist_rate": 0,
            "by_trigger": [],
            "by_hour": [],
            "by_day": [],
            "avg_intensity": 0,
            "intensity_trend": [],
            "top_trigger": None,
            "worst_hour": None,
            "insights": [],
        }

    total = len(records)
    resisted = len([r for r in records if r.resisted])
    resist_rate = round(resisted / total * 100, 1) if total > 0 else 0

    # By trigger
    trigger_counts: dict[str, dict] = {}
    for r in records:
        if r.trigger not in trigger_counts:
            trigger_counts[r.trigger] = {"count": 0, "resisted": 0, "total_intensity": 0}
        trigger_counts[r.trigger]["count"] += 1
        trigger_counts[r.trigger]["total_intensity"] += r.intensity
        if r.resisted:
            trigger_counts[r.trigger]["resisted"] += 1

    by_trigger = [
        {
            "trigger": t,
            "count": d["count"],
            "resisted": d["resisted"],
            "resist_rate": round(d["resisted"] / d["count"] * 100, 1),
            "avg_intensity": round(d["total_intensity"] / d["count"], 1),
        }
        for t, d in sorted(trigger_counts.items(), key=lambda x: x[1]["count"], reverse=True)
    ]

    # By hour of day
    hour_counts = [0] * 24
    for r in records:
        ts = r.timestamp.astimezone(TZ) if r.timestamp.tzinfo else r.timestamp.replace(tzinfo=TZ)
        hour_counts[ts.hour] += 1
    by_hour = [{"hour": h, "count": c} for h, c in enumerate(hour_counts)]

    # By day of week (0=Monday)
    day_counts = [0] * 7
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for r in records:
        ts = r.timestamp.astimezone(TZ) if r.timestamp.tzinfo else r.timestamp.replace(tzinfo=TZ)
        day_counts[ts.weekday()] += 1
    by_day = [{"day": day_names[d], "count": c} for d, c in enumerate(day_counts)]

    # Average intensity
    avg_intensity = round(sum(r.intensity for r in records) / total, 1)

    # Intensity trend (last 7 days, daily average)
    intensity_trend = []
    for days_ago in range(6, -1, -1):
        day = (now - timedelta(days=days_ago)).date()
        day_records = [
            r for r in records
            if (r.timestamp.astimezone(TZ) if r.timestamp.tzinfo else r.timestamp.replace(tzinfo=TZ)).date() == day
        ]
        if day_records:
            avg = round(sum(r.intensity for r in day_records) / len(day_records), 1)
            intensity_trend.append({"date": day.isoformat(), "avg_intensity": avg, "count": len(day_records)})
        else:
            intensity_trend.append({"date": day.isoformat(), "avg_intensity": 0, "count": 0})

    # Insights
    insights = []
    top_trigger = by_trigger[0]["trigger"] if by_trigger else None
    worst_hour = max(range(24), key=lambda h: hour_counts[h]) if any(hour_counts) else None

    if top_trigger:
        top_data = by_trigger[0]
        insights.append(f"Your #1 trigger is '{top_trigger}' ({top_data['count']} times, {top_data['resist_rate']}% resisted)")
    if worst_hour is not None and hour_counts[worst_hour] > 0:
        insights.append(f"Peak craving hour: {worst_hour:02d}:00 ({hour_counts[worst_hour]} cravings)")
    if resist_rate >= 80:
        insights.append(f"Great resist rate: {resist_rate}%! You're in control.")
    elif resist_rate >= 50:
        insights.append(f"Resist rate: {resist_rate}%. Getting stronger!")
    if avg_intensity > 0:
        recent_week = [r for r in records if (now - r.timestamp.astimezone(TZ)).days < 7]
        older = [r for r in records if (now - r.timestamp.astimezone(TZ)).days >= 7]
        if recent_week and older:
            recent_avg = sum(r.intensity for r in recent_week) / len(recent_week)
            older_avg = sum(r.intensity for r in older) / len(older)
            if recent_avg < older_avg:
                insights.append(f"Cravings are getting weaker (avg {recent_avg:.1f} vs {older_avg:.1f} before)")

    return {
        "total_cravings": total,
        "resisted_count": resisted,
        "resist_rate": resist_rate,
        "by_trigger": by_trigger,
        "by_hour": by_hour,
        "by_day": by_day,
        "avg_intensity": avg_intensity,
        "intensity_trend": intensity_trend,
        "top_trigger": top_trigger,
        "worst_hour": worst_hour,
        "insights": insights,
    }


@app.get("/api/cravings/triggers")
async def get_craving_triggers():
    """Return the list of valid craving triggers."""
    return {"triggers": CRAVING_TRIGGERS}


# ---------------------------------------------------------------------------
# Weekly Report Card
# ---------------------------------------------------------------------------

@app.get("/api/report/weekly")
async def get_weekly_report():
    """Detailed weekly report card with insights."""
    engine = _get_engine()
    config = config_store.load()
    entries = entry_store.load()
    now = _now()

    # Current week boundaries
    week_start = engine.current_week_start(now)
    week_end = week_start + timedelta(days=7)
    today = now.date()

    # Previous week boundaries
    prev_week_start = week_start - timedelta(weeks=1)
    prev_week_end = week_start

    # Entries for current and previous week
    this_week_entries = [
        e for e in entries
        if week_start <= e.timestamp.astimezone(TZ) < week_end
    ]
    prev_week_entries = [
        e for e in entries
        if prev_week_start <= e.timestamp.astimezone(TZ) < prev_week_end
    ]

    # --- Daily breakdown for this week ---
    daily_breakdown = []
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    best_day = None
    best_day_count = float('inf')
    worst_day = None
    worst_day_count = -1

    for i in range(7):
        day_date = (week_start + timedelta(days=i)).date()
        if day_date > today:
            break

        day_entries = [
            e for e in this_week_entries
            if e.timestamp.astimezone(TZ).date() == day_date
        ]
        regular = len([e for e in day_entries if not e.is_bonus])
        bonus = len([e for e in day_entries if e.is_bonus])
        day_dt = datetime.combine(day_date, datetime.min.time(), tzinfo=TZ)
        allowance = engine.daily_allowance(day_dt)
        under_budget = allowance - regular

        daily_breakdown.append({
            "date": day_date.isoformat(),
            "day_name": day_names[i],
            "smoked": regular,
            "bonus": bonus,
            "allowance": allowance,
            "under_budget": under_budget,
        })

        if regular < best_day_count:
            best_day_count = regular
            best_day = day_names[i]
        if regular > worst_day_count:
            worst_day_count = regular
            worst_day = day_names[i]

    # --- Totals ---
    this_week_regular = len([e for e in this_week_entries if not e.is_bonus])
    this_week_bonus = len([e for e in this_week_entries if e.is_bonus])
    prev_week_regular = len([e for e in prev_week_entries if not e.is_bonus])

    # Days elapsed this week
    days_elapsed = min(7, (today - week_start.date()).days + 1)
    days_elapsed_prev = 7

    # Daily averages
    avg_this_week = round(this_week_regular / days_elapsed, 1) if days_elapsed > 0 else 0
    avg_prev_week = round(prev_week_regular / days_elapsed_prev, 1) if days_elapsed_prev > 0 else 0
    trend = round(avg_this_week - avg_prev_week, 1)

    # --- Longest gap between cigarettes this week ---
    week_non_bonus = sorted(
        [e for e in this_week_entries if not e.is_bonus],
        key=lambda e: e.timestamp,
    )
    longest_gap_hours = 0.0
    if len(week_non_bonus) >= 2:
        for j in range(1, len(week_non_bonus)):
            gap = (week_non_bonus[j].timestamp.astimezone(TZ) - week_non_bonus[j-1].timestamp.astimezone(TZ)).total_seconds() / 3600
            if gap > longest_gap_hours:
                longest_gap_hours = gap
    elif len(week_non_bonus) == 1:
        # Gap from start of week to first entry, or from last entry to now
        gap_to_now = (now - week_non_bonus[0].timestamp.astimezone(TZ)).total_seconds() / 3600
        gap_from_start = (week_non_bonus[0].timestamp.astimezone(TZ) - week_start).total_seconds() / 3600
        longest_gap_hours = max(gap_to_now, gap_from_start)

    # --- Week allowance total ---
    week_allowance_total = engine.daily_allowance(now) * days_elapsed
    total_under_budget = week_allowance_total - this_week_regular

    # --- Achievements ---
    achievements = []
    if total_under_budget > 0:
        achievements.append(f"🏆 {total_under_budget} under budget this week")
    if best_day_count == 0 and days_elapsed > 0:
        achievements.append(f"⭐ Zero-cigarette day: {best_day}!")
    if longest_gap_hours >= 12:
        achievements.append(f"⏱️ Longest gap: {longest_gap_hours:.1f}h — great restraint!")
    if trend < 0:
        achievements.append(f"📉 Averaging {abs(trend):.1f} fewer/day than last week")
    if this_week_bonus == 0 and days_elapsed >= 3:
        achievements.append("🎁 No bonus used this week (so far)")

    # --- Comparison to previous week ---
    comparison = {
        "this_week_total": this_week_regular,
        "prev_week_total": prev_week_regular,
        "difference": this_week_regular - prev_week_regular,
        "this_week_avg": avg_this_week,
        "prev_week_avg": avg_prev_week,
        "trend": "improving" if trend < 0 else "same" if trend == 0 else "higher",
    }

    # --- Grade ---
    if days_elapsed >= 1:
        compliance = total_under_budget / (week_allowance_total or 1)
        if compliance >= 0.2:
            grade = "A"
        elif compliance >= 0:
            grade = "B"
        elif compliance >= -0.1:
            grade = "C"
        else:
            grade = "D"
    else:
        grade = "—"

    return {
        "week_index": engine.current_week_index(now) + 1,
        "week_start": week_start.date().isoformat(),
        "days_elapsed": days_elapsed,
        "grade": grade,
        "daily_breakdown": daily_breakdown,
        "totals": {
            "smoked": this_week_regular,
            "bonus_used": this_week_bonus,
            "allowance": week_allowance_total,
            "under_budget": total_under_budget,
        },
        "longest_gap_hours": round(longest_gap_hours, 1),
        "best_day": best_day,
        "worst_day": worst_day,
        "avg_per_day": avg_this_week,
        "comparison": comparison,
        "achievements": achievements,
    }


# ---------------------------------------------------------------------------
# Static files (frontend)
# ---------------------------------------------------------------------------

FRONTEND_DIR = "/app/frontend/dist"
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
