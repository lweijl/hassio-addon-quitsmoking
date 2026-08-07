"""Craving journal routes: log_craving, get_cravings, get_craving_patterns, get_craving_triggers."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..engine import TZ
from ..state import _now

router = APIRouter()

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

    def __init__(self) -> None:
        from ..persistence import DATA_DIR, _atomic_write
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


@router.post("/api/cravings")
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


@router.get("/api/cravings")
async def get_cravings():
    """Return all craving entries."""
    records = craving_store.load()
    return {"cravings": [r.model_dump(mode="json") for r in records]}


@router.get("/api/cravings/patterns")
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


@router.get("/api/cravings/triggers")
async def get_craving_triggers():
    """Return the list of valid craving triggers."""
    return {"triggers": CRAVING_TRIGGERS}
