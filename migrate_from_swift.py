#!/usr/bin/env python3
"""Migrate data from the macOS QuitSmoking Swift app to the HA addon format.

Usage:
    python3 migrate_from_swift.py [--source-dir DIR] [--output-dir DIR]

Defaults:
    --source-dir: ~/Library/Application Support/QuitSmoking/
    --output-dir: ./migrated_data/

The output directory will contain:
    - config.json   (HA addon format)
    - entries.json  (HA addon format)

To inject into the running HA addon:
    1. Copy to your HA config directory: scp migrated_data/* ha-host:/config/quitsmoking/
    2. Restart the addon

Or use the addon's /api/import endpoint (if available):
    curl -X POST http://your-ha:8099/api/import \
         -H "Content-Type: application/json" \
         -d @migrated_data/entries.json
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from uuid import UUID

DEFAULT_SOURCE = Path.home() / "Library" / "Application Support" / "QuitSmoking"
DEFAULT_OUTPUT = Path.cwd() / "migrated_data"


def parse_time_string(time_str: str) -> int:
    """Convert 'HH:mm' to minutes from midnight."""
    parts = time_str.split(":")
    return int(parts[0]) * 60 + int(parts[1])


def migrate_config(source_dir: Path) -> dict:
    """Convert Swift config.json to HA addon format."""
    config_path = source_dir / "config.json"
    if not config_path.exists():
        print(f"⚠️  No config.json found at {config_path}, using defaults")
        return None

    with open(config_path) as f:
        swift_config = json.load(f)

    # Convert weekly schedules
    schedules = []
    for s in swift_config.get("weeklySchedules", []):
        mode = s["mode"]
        if mode == "daily":
            schedules.append({"mode": "daily", "allowance": s["allowance"]})
        elif mode == "interval":
            schedules.append({"mode": "interval", "interval_hours": s["hours"]})
        elif mode == "quit":
            schedules.append({"mode": "quit"})

    # Convert time strings to minutes
    window_start = parse_time_string(swift_config.get("smokingWindowStart", "07:30"))
    window_end = parse_time_string(swift_config.get("smokingWindowEnd", "22:30"))

    ha_config = {
        "start_date": swift_config["startDate"],
        "weekly_schedules": schedules,
        "bonus_per_week": swift_config.get("bonusPerWeek", 1),
        "cost_per_cigarette": swift_config.get("costPerCigarette", 0.565),
        "baseline_daily_count": swift_config.get("baselineDailyCount", 20),
        "smoking_window_start_minutes": window_start,
        "smoking_window_end_minutes": window_end,
    }

    return ha_config


def migrate_entries(source_dir: Path) -> list[dict]:
    """Convert Swift entries.json to HA addon format."""
    entries_path = source_dir / "entries.json"
    if not entries_path.exists():
        print(f"⚠️  No entries.json found at {entries_path}")
        return []

    with open(entries_path) as f:
        swift_data = json.load(f)

    # Swift format wraps entries in {"version": 1, "entries": [...]}
    swift_entries = swift_data.get("entries", [])

    ha_entries = []
    for entry in swift_entries:
        ha_entries.append({
            "id": entry["id"].lower(),  # Normalize UUID to lowercase
            "timestamp": entry["timestamp"],  # Already ISO 8601
            "is_bonus": entry.get("isBonus", False),
        })

    return ha_entries


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Migrate QuitSmoking data from Swift app to HA addon")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE,
                        help=f"Source directory (default: {DEFAULT_SOURCE})")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT,
                        help=f"Output directory (default: {DEFAULT_OUTPUT})")
    args = parser.parse_args()

    source = args.source_dir
    output = args.output_dir

    if not source.exists():
        print(f"❌ Source directory not found: {source}")
        sys.exit(1)

    output.mkdir(parents=True, exist_ok=True)

    # Migrate config
    config = migrate_config(source)
    if config:
        config_out = output / "config.json"
        with open(config_out, "w") as f:
            json.dump(config, f, indent=2)
        print(f"✅ Config migrated → {config_out}")
        print(f"   Start date: {config['start_date']}")
        print(f"   Weeks: {len(config['weekly_schedules'])}")
    else:
        print("ℹ️  Skipped config (not found, addon will use defaults)")

    # Migrate entries
    entries = migrate_entries(source)
    if entries:
        entries_out = output / "entries.json"
        with open(entries_out, "w") as f:
            json.dump(entries, f, indent=2)
        print(f"✅ Entries migrated → {entries_out}")
        print(f"   Total entries: {len(entries)}")
        bonus_count = sum(1 for e in entries if e["is_bonus"])
        print(f"   Regular: {len(entries) - bonus_count}, Bonus: {bonus_count}")
        if entries:
            first = entries[0]["timestamp"]
            last = entries[-1]["timestamp"]
            print(f"   Date range: {first[:10]} → {last[:10]}")
    else:
        print("ℹ️  No entries to migrate")

    print()
    print("📋 Next steps:")
    print(f"   1. Copy files to your HA host:")
    print(f"      scp {output}/config.json {output}/entries.json your-ha-host:/config/quitsmoking/")
    print(f"   2. Restart the Quit Smoking addon")
    print(f"   3. Verify data appears in the web UI")


if __name__ == "__main__":
    main()
