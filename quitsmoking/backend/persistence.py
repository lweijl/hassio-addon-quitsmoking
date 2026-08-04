"""JSON file persistence with atomic writes."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Optional

from .engine import (
    ScheduleConfig,
    ScheduleMode,
    WeekSchedule,
    default_config,
)
from .models import CigaretteEntry

DATA_DIR = Path(os.environ.get("DATA_DIR", "/config/quitsmoking"))


def _ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _atomic_write(path: Path, data: str) -> None:
    """Write data atomically: write to temp file then rename."""
    _ensure_dir(path)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# EntryStore
# ---------------------------------------------------------------------------

class EntryStore:
    def __init__(self, data_dir: Optional[Path] = None):
        self.path = (data_dir or DATA_DIR) / "entries.json"

    def load(self) -> list[CigaretteEntry]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return [CigaretteEntry(**entry) for entry in raw]
        except (json.JSONDecodeError, KeyError, ValueError):
            return []

    def save(self, entries: list[CigaretteEntry]) -> None:
        data = [entry.model_dump(mode="json") for entry in entries]
        _atomic_write(self.path, json.dumps(data, indent=2, default=str))

    def add_entry(self, entry: CigaretteEntry) -> CigaretteEntry:
        entries = self.load()
        entries.append(entry)
        self.save(entries)
        return entry

    def remove_last(self) -> Optional[CigaretteEntry]:
        entries = self.load()
        if not entries:
            return None
        removed = entries.pop()
        self.save(entries)
        return removed


# ---------------------------------------------------------------------------
# ConfigStore
# ---------------------------------------------------------------------------

def _schedule_to_dict(s: WeekSchedule) -> dict:
    if s.mode == ScheduleMode.DAILY:
        return {"mode": "daily", "allowance": s.allowance}
    elif s.mode == ScheduleMode.INTERVAL:
        return {"mode": "interval", "interval_hours": s.interval_hours}
    else:
        return {"mode": "quit"}


def _dict_to_schedule(d: dict) -> WeekSchedule:
    mode = d["mode"]
    if mode == "daily":
        return WeekSchedule.daily(d["allowance"])
    elif mode == "interval":
        return WeekSchedule.interval(d["interval_hours"])
    else:
        return WeekSchedule.quit()


class ConfigStore:
    def __init__(self, data_dir: Optional[Path] = None):
        self.path = (data_dir or DATA_DIR) / "config.json"

    def load(self) -> ScheduleConfig:
        if not self.path.exists():
            return default_config()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return ScheduleConfig(
                start_date=date.fromisoformat(raw["start_date"]),
                weekly_schedules=[_dict_to_schedule(s) for s in raw["weekly_schedules"]],
                bonus_per_week=raw.get("bonus_per_week", 1),
                cost_per_cigarette=raw.get("cost_per_cigarette", 0.565),
                baseline_daily_count=raw.get("baseline_daily_count", 20),
                smoking_window_start_minutes=raw.get("smoking_window_start_minutes", 450),
                smoking_window_end_minutes=raw.get("smoking_window_end_minutes", 1350),
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            return default_config()

    def save(self, config: ScheduleConfig) -> None:
        data = {
            "start_date": config.start_date.isoformat(),
            "weekly_schedules": [_schedule_to_dict(s) for s in config.weekly_schedules],
            "bonus_per_week": config.bonus_per_week,
            "cost_per_cigarette": config.cost_per_cigarette,
            "baseline_daily_count": config.baseline_daily_count,
            "smoking_window_start_minutes": config.smoking_window_start_minutes,
            "smoking_window_end_minutes": config.smoking_window_end_minutes,
        }
        _atomic_write(self.path, json.dumps(data, indent=2))
