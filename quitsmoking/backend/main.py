"""FastAPI application for QuitSmoking Home Assistant add-on."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from zoneinfo import ZoneInfo

from .engine import ScheduleEngine, ScheduleMode, TZ, WeekSchedule
from .models import (
    CigaretteEntry,
    ConfigUpdate,
    HistoryEntry,
    LogRequest,
    StatusResponse,
)
from .notifications import send_notification
from .persistence import ConfigStore, EntryStore

INGRESS_PATH = os.environ.get("INGRESS_PATH", "")

app = FastAPI(title="QuitSmoking", root_path=INGRESS_PATH)

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
    last_entry_ts = non_bonus_entries[-1].timestamp if non_bonus_entries else None

    can_smoke = engine.can_smoke_now(last_entry_ts, now)
    time_until = engine.time_until_next(last_entry_ts, now)
    next_allowed = engine.next_allowed_time(last_entry_ts, now)

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
    return _build_status(engine, entries)


@app.post("/api/log", response_model=StatusResponse)
async def log_cigarette(req: LogRequest):
    engine = _get_engine()
    now = _now()

    entry = CigaretteEntry(
        id=uuid4(),
        timestamp=now,
        is_bonus=req.is_bonus,
    )
    entry_store.add_entry(entry)

    entries = entry_store.load()
    status = _build_status(engine, entries)

    # Send notification
    if req.is_bonus:
        await send_notification(
            "🚬 Bonus used",
            f"Bonus cigarette logged. {status.remaining_bonus} bonus remaining this week.",
        )
    else:
        if status.remaining_today == 0:
            await send_notification(
                "⚠️ Daily limit reached",
                "You've used all your regular cigarettes for today.",
            )
        else:
            await send_notification(
                "🚬 Cigarette logged",
                f"{status.remaining_today} remaining today.",
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
    from collections import defaultdict
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

        from .engine import ScheduleConfig
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
        from .engine import ScheduleConfig
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
# Static files (frontend)
# ---------------------------------------------------------------------------

FRONTEND_DIR = "/app/frontend/dist"
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
