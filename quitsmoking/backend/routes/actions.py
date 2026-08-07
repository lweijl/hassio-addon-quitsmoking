"""Notification action routes: action_log_cigarette, action_log_bonus, action_skip."""

from __future__ import annotations

from random import choice
from uuid import uuid4

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..engine import TZ
from ..models import CigaretteEntry
from ..notifications import send_notification, Actions
from ..state import (
    _get_engine,
    _now,
    _build_status,
    _entries_this_week,
    entry_store,
)

router = APIRouter()


@router.get("/api/actions/log")
@router.post("/api/actions/log")
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


@router.get("/api/actions/log_bonus")
@router.post("/api/actions/log_bonus")
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


@router.get("/api/actions/skip")
@router.post("/api/actions/skip")
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
