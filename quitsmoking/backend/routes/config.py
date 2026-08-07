"""Config routes: get_config, update_config, import_entries, import_config."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..engine import ScheduleConfig, ScheduleMode, TZ, WeekSchedule
from ..models import CigaretteEntry, ConfigUpdate
from ..state import config_store, entry_store, notify_service_store

router = APIRouter()


@router.get("/api/config")
async def get_config():
    config = await config_store.load()
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


@router.put("/api/config")
async def update_config(update: ConfigUpdate):
    config = await config_store.load()

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

    await config_store.save(config)
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Import (migrate from Swift app or restore backup)
# ---------------------------------------------------------------------------

class ImportEntriesRequest(BaseModel):
    """Accepts either the Swift app format or the HA addon format."""
    # Swift format: {"version": 1, "entries": [...]}
    version: Optional[int] = None
    entries: Optional[list[dict]] = None


@router.post("/api/import/entries")
async def import_entries(request: Request):
    """Import entries from the Swift macOS app or a previous export.

    Accepts:
      - Swift format: {"version": 1, "entries": [{"id": "...", "timestamp": "...", "isBonus": false}]}
      - HA addon format: [{"id": "...", "timestamp": "...", "is_bonus": false}]
    """
    body_bytes = await request.body()
    if len(body_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Request body too large (max 5MB)")
    body = json.loads(body_bytes)

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
    existing = await entry_store.load()
    existing_ids = {str(e.id) for e in existing}
    new_entries = [e for e in imported if str(e.id) not in existing_ids]

    all_entries = existing + new_entries
    # Sort by timestamp
    all_entries.sort(key=lambda e: e.timestamp)
    await entry_store.save(all_entries)

    return {
        "status": "ok",
        "imported": len(new_entries),
        "skipped_duplicates": len(imported) - len(new_entries),
        "total": len(all_entries),
    }


@router.post("/api/import/config")
async def import_config(request: Request):
    """Import config from the Swift macOS app or a previous export.

    Accepts both Swift format (camelCase) and HA addon format (snake_case).
    """
    body_bytes = await request.body()
    if len(body_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Request body too large (max 5MB)")
    body = json.loads(body_bytes)

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

    await config_store.save(config)
    return {
        "status": "ok",
        "start_date": config.start_date.isoformat(),
        "weeks": len(config.weekly_schedules),
    }


# ---------------------------------------------------------------------------
# Notification service management
# ---------------------------------------------------------------------------

class NotifyServicesUpdate(BaseModel):
    """Request model for updating notification services."""
    services: list[str]


@router.get("/api/config/notify-services")
async def get_notify_services():
    """Get configured notification services."""
    services = await notify_service_store.get_services()
    return {"services": services}


@router.put("/api/config/notify-services")
async def update_notify_services(body: NotifyServicesUpdate):
    """Update notification services list."""
    # Clean up entries
    services = [s.strip() for s in body.services if isinstance(s, str) and s.strip()]
    await notify_service_store.save_services(services)
    return {"status": "ok", "services": services}
