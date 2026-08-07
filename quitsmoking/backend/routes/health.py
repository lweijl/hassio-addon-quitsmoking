"""Health timeline routes: get_health_timeline."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter

from ..engine import TZ
from ..state import _now, config_store, entry_store

router = APIRouter()

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


@router.get("/api/health-timeline")
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
