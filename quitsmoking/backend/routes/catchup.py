"""Catch-up routes: get_catchup, backfill_days."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel

from ..engine import TZ
from ..models import CigaretteEntry
from ..state import _get_engine, _now, config_store, entry_store

router = APIRouter()


class BackfillDay(BaseModel):
    date: str
    count: int
    is_bonus: bool = False


class BackfillRequest(BaseModel):
    days: list[BackfillDay]


@router.get("/api/catchup")
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


@router.post("/api/catchup/backfill")
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
