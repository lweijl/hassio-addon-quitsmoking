"""Shared application state: stores, engine getter, and common helpers."""

from __future__ import annotations

from datetime import datetime

from .engine import ScheduleEngine, ScheduleMode, TZ
from .models import CigaretteEntry, StatusResponse
from .persistence_db import ConfigStore, EntryStore, NotifyServiceStore

# Stores (singleton-like)
entry_store = EntryStore()
config_store = ConfigStore()
notify_service_store = NotifyServiceStore()


async def _get_engine() -> ScheduleEngine:
    config = await config_store.load()
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
