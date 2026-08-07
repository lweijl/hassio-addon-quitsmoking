"""Async SQLite persistence layer for QuitSmoking.

Replaces JSON file persistence with aiosqlite for:
- Non-blocking async I/O
- Built-in locking (no race conditions)
- Indexed queries (faster aggregations)
- Atomic transactions

Auto-migrates from JSON files on first startup.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from uuid import UUID

import aiosqlite

from .engine import (
    ScheduleConfig,
    ScheduleMode,
    WeekSchedule,
    default_config,
)
from .models import CigaretteEntry

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("DATA_DIR", "/config/quitsmoking"))
DB_PATH = DATA_DIR / "quitsmoking.db"


# ---------------------------------------------------------------------------
# Database initialization
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    is_bonus INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cravings (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    trigger_type TEXT NOT NULL,
    intensity INTEGER NOT NULL DEFAULT 3,
    notes TEXT,
    resisted INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sent_notifications (
    key TEXT PRIMARY KEY,
    sent_date TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_entries_timestamp ON entries(timestamp);
CREATE INDEX IF NOT EXISTS idx_cravings_timestamp ON cravings(timestamp);
CREATE INDEX IF NOT EXISTS idx_cravings_trigger ON cravings(trigger_type);
CREATE INDEX IF NOT EXISTS idx_sent_date ON sent_notifications(sent_date);
"""


async def init_db() -> None:
    """Initialize the database schema."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()
    logger.info("Database initialized at %s", DB_PATH)


async def _get_db() -> aiosqlite.Connection:
    """Get a database connection."""
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    return db


# ---------------------------------------------------------------------------
# EntryStore (async)
# ---------------------------------------------------------------------------

class EntryStore:
    """Async SQLite-backed entry store."""

    async def load(self) -> list[CigaretteEntry]:
        """Load all entries sorted by timestamp."""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, timestamp, is_bonus FROM entries ORDER BY timestamp"
            ) as cursor:
                rows = await cursor.fetchall()
                return [
                    CigaretteEntry(
                        id=row["id"],
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        is_bonus=bool(row["is_bonus"]),
                    )
                    for row in rows
                ]

    async def add_entry(self, entry: CigaretteEntry) -> CigaretteEntry:
        """Add a single entry."""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO entries (id, timestamp, is_bonus) VALUES (?, ?, ?)",
                (str(entry.id), entry.timestamp.isoformat(), int(entry.is_bonus)),
            )
            await db.commit()
        return entry

    async def save(self, entries: list[CigaretteEntry]) -> None:
        """Replace all entries (used for imports/backfill)."""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM entries")
            await db.executemany(
                "INSERT INTO entries (id, timestamp, is_bonus) VALUES (?, ?, ?)",
                [(str(e.id), e.timestamp.isoformat(), int(e.is_bonus)) for e in entries],
            )
            await db.commit()

    async def remove_last(self) -> Optional[CigaretteEntry]:
        """Remove the most recent entry."""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, timestamp, is_bonus FROM entries ORDER BY timestamp DESC LIMIT 1"
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                entry = CigaretteEntry(
                    id=row["id"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    is_bonus=bool(row["is_bonus"]),
                )
            await db.execute("DELETE FROM entries WHERE id = ?", (str(entry.id),))
            await db.commit()
        return entry

    async def count(self) -> int:
        """Get total entry count."""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT COUNT(*) FROM entries") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0


# ---------------------------------------------------------------------------
# ConfigStore (async)
# ---------------------------------------------------------------------------

class ConfigStore:
    """Async SQLite-backed config store."""

    async def load(self) -> ScheduleConfig:
        """Load schedule config from DB."""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT key, value FROM config"
            ) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            return default_config()

        data = {row["key"]: row["value"] for row in rows}

        if "schedule_json" not in data:
            return default_config()

        try:
            raw = json.loads(data["schedule_json"])
            schedules = [_dict_to_schedule(s) for s in raw]
            return ScheduleConfig(
                start_date=date.fromisoformat(data.get("start_date", "2026-06-15")),
                weekly_schedules=schedules,
                bonus_per_week=int(data.get("bonus_per_week", "1")),
                cost_per_cigarette=float(data.get("cost_per_cigarette", "0.565")),
                baseline_daily_count=int(data.get("baseline_daily_count", "20")),
                smoking_window_start_minutes=int(data.get("smoking_window_start_minutes", "450")),
                smoking_window_end_minutes=int(data.get("smoking_window_end_minutes", "1350")),
            )
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.error("Failed to load config from DB: %s", exc)
            return default_config()

    async def save(self, config: ScheduleConfig) -> None:
        """Save schedule config to DB."""
        schedule_json = json.dumps([_schedule_to_dict(s) for s in config.weekly_schedules])

        pairs = [
            ("start_date", config.start_date.isoformat()),
            ("schedule_json", schedule_json),
            ("bonus_per_week", str(config.bonus_per_week)),
            ("cost_per_cigarette", str(config.cost_per_cigarette)),
            ("baseline_daily_count", str(config.baseline_daily_count)),
            ("smoking_window_start_minutes", str(config.smoking_window_start_minutes)),
            ("smoking_window_end_minutes", str(config.smoking_window_end_minutes)),
        ]

        async with aiosqlite.connect(DB_PATH) as db:
            await db.executemany(
                "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
                pairs,
            )
            await db.commit()


# ---------------------------------------------------------------------------
# CravingStore (async)
# ---------------------------------------------------------------------------

class CravingRecord:
    """In-memory craving record."""

    def __init__(
        self,
        id: UUID,
        timestamp: datetime,
        trigger: str,
        intensity: int,
        notes: Optional[str],
        resisted: bool,
    ):
        self.id = id
        self.timestamp = timestamp
        self.trigger = trigger
        self.intensity = intensity
        self.notes = notes
        self.resisted = resisted

    def model_dump(self, mode: str = "json") -> dict:
        """Serialize for API responses."""
        return {
            "id": str(self.id),
            "timestamp": self.timestamp.isoformat(),
            "trigger": self.trigger,
            "intensity": self.intensity,
            "notes": self.notes,
            "resisted": self.resisted,
        }


class CravingStore:
    """Async SQLite-backed craving store."""

    async def load(self) -> list[CravingRecord]:
        """Load all cravings sorted by timestamp."""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, timestamp, trigger_type, intensity, notes, resisted "
                "FROM cravings ORDER BY timestamp"
            ) as cursor:
                rows = await cursor.fetchall()
                return [
                    CravingRecord(
                        id=UUID(row["id"]),
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        trigger=row["trigger_type"],
                        intensity=row["intensity"],
                        notes=row["notes"],
                        resisted=bool(row["resisted"]),
                    )
                    for row in rows
                ]

    async def add(self, record: CravingRecord) -> None:
        """Add a craving record."""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO cravings (id, timestamp, trigger_type, intensity, notes, resisted) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(record.id),
                    record.timestamp.isoformat(),
                    record.trigger,
                    record.intensity,
                    record.notes,
                    int(record.resisted),
                ),
            )
            await db.commit()


# ---------------------------------------------------------------------------
# SentNotificationStore (async)
# ---------------------------------------------------------------------------

class SentNotificationStore:
    """Async SQLite-backed sent notification tracking."""

    async def was_sent(self, key: str) -> bool:
        """Check if a notification key exists."""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT 1 FROM sent_notifications WHERE key = ?", (key,)
            ) as cursor:
                return await cursor.fetchone() is not None

    async def mark_sent(self, key: str, today: str) -> None:
        """Mark a notification as sent."""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO sent_notifications (key, sent_date) VALUES (?, ?)",
                (key, today),
            )
            # Clean up old entries (not from today) — but only date-based keys
            await db.execute(
                "DELETE FROM sent_notifications WHERE sent_date != ? "
                "AND key NOT LIKE 'interval_elapsed:%'",
                (today,),
            )
            await db.commit()

    async def clear_old(self, today: str) -> None:
        """Remove entries from previous days (except interval keys)."""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM sent_notifications WHERE sent_date != ? "
                "AND key NOT LIKE 'interval_elapsed:%'",
                (today,),
            )
            await db.commit()


# ---------------------------------------------------------------------------
# Migration from JSON
# ---------------------------------------------------------------------------

async def migrate_from_json() -> None:
    """Migrate existing JSON files to SQLite if they exist.

    Renames JSON files to .migrated after successful import.
    """
    entries_path = DATA_DIR / "entries.json"
    config_path = DATA_DIR / "config.json"
    cravings_path = DATA_DIR / "cravings.json"
    sent_path = DATA_DIR / "sent_notifications.json"

    migrated_any = False

    # Migrate entries
    if entries_path.exists():
        try:
            raw = json.loads(entries_path.read_text(encoding="utf-8"))
            entries = [CigaretteEntry(**e) for e in raw]
            store = EntryStore()
            await store.save(entries)
            entries_path.rename(entries_path.with_suffix(".json.migrated"))
            logger.info("Migrated %d entries from JSON to SQLite", len(entries))
            migrated_any = True
        except Exception as exc:
            logger.error("Failed to migrate entries: %s", exc)

    # Migrate config
    if config_path.exists():
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
            config = ScheduleConfig(
                start_date=date.fromisoformat(raw["start_date"]),
                weekly_schedules=[_dict_to_schedule(s) for s in raw["weekly_schedules"]],
                bonus_per_week=raw.get("bonus_per_week", 1),
                cost_per_cigarette=raw.get("cost_per_cigarette", 0.565),
                baseline_daily_count=raw.get("baseline_daily_count", 20),
                smoking_window_start_minutes=raw.get("smoking_window_start_minutes", 450),
                smoking_window_end_minutes=raw.get("smoking_window_end_minutes", 1350),
            )
            store = ConfigStore()
            await store.save(config)
            config_path.rename(config_path.with_suffix(".json.migrated"))
            logger.info("Migrated config from JSON to SQLite")
            migrated_any = True
        except Exception as exc:
            logger.error("Failed to migrate config: %s", exc)

    # Migrate cravings
    if cravings_path.exists():
        try:
            raw = json.loads(cravings_path.read_text(encoding="utf-8"))
            store = CravingStore()
            for r in raw:
                record = CravingRecord(
                    id=UUID(r["id"]),
                    timestamp=datetime.fromisoformat(r["timestamp"]),
                    trigger=r["trigger"],
                    intensity=r["intensity"],
                    notes=r.get("notes"),
                    resisted=r.get("resisted", True),
                )
                await store.add(record)
            cravings_path.rename(cravings_path.with_suffix(".json.migrated"))
            logger.info("Migrated %d cravings from JSON to SQLite", len(raw))
            migrated_any = True
        except Exception as exc:
            logger.error("Failed to migrate cravings: %s", exc)

    # Migrate sent notifications
    if sent_path.exists():
        try:
            raw = json.loads(sent_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                async with aiosqlite.connect(DB_PATH) as db:
                    today = datetime.now().date().isoformat()
                    await db.executemany(
                        "INSERT OR REPLACE INTO sent_notifications (key, sent_date) VALUES (?, ?)",
                        [(key, today) for key in raw],
                    )
                    await db.commit()
            sent_path.rename(sent_path.with_suffix(".json.migrated"))
            logger.info("Migrated sent notifications from JSON to SQLite")
            migrated_any = True
        except Exception as exc:
            logger.error("Failed to migrate sent notifications: %s", exc)

    if migrated_any:
        logger.info("JSON → SQLite migration complete")


# ---------------------------------------------------------------------------
# Helpers
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
