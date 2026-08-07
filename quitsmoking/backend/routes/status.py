"""Status routes: get_status, log_cigarette, undo_last."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ..engine import TZ
from ..models import CigaretteEntry, LogRequest, StatusResponse
from ..notifications import send_notification, Actions
from ..state import _get_engine, _now, _build_status, entry_store

router = APIRouter()


@router.get("/api/status", response_model=StatusResponse)
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


@router.post("/api/log", response_model=StatusResponse)
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


@router.post("/api/undo", response_model=StatusResponse)
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
