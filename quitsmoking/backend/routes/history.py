"""History routes: get_history, get_history_entries, get_progress, get_weekly_report."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter

from ..engine import TZ
from ..models import HistoryEntry
from ..state import _get_engine, _now, _entries_today, config_store, entry_store

router = APIRouter()

# ---------------------------------------------------------------------------
# Progress / Savings constants
# ---------------------------------------------------------------------------

FUN_EQUIVALENTS = [
    ("Coffee ☕", 3.50),
    ("Pizza 🍕", 12.0),
    ("Movie ticket 🎬", 14.0),
    ("Book 📚", 20.0),
    ("Concert ticket 🎵", 65.0),
    ("Weekend trip 🧳", 200.0),
    ("New phone 📱", 800.0),
]

MILESTONES_AVOIDED = [100, 250, 500, 1000, 2000, 5000]
MILESTONES_SAVED = [50, 100, 200, 500, 1000, 2000]


@router.get("/api/history")
async def get_history():
    """Return daily aggregated history for the chart.

    Returns: {"days": [{"date": "2026-06-15", "count": 8, "bonus_count": 0, "allowance": 8}, ...]}
    """
    engine = _get_engine()
    entries = entry_store.load()

    if not entries:
        return {"days": []}

    # Aggregate entries by date
    daily: dict[str, dict] = defaultdict(lambda: {"count": 0, "bonus_count": 0})

    for e in entries:
        ts = e.timestamp.astimezone(TZ) if e.timestamp.tzinfo else e.timestamp.replace(tzinfo=TZ)
        day_key = ts.date().isoformat()
        daily[day_key]["count"] += 1
        if e.is_bonus:
            daily[day_key]["bonus_count"] += 1

    # Build day-by-day from start to today
    config = config_store.load()
    start = config.start_date
    today = _now().date()
    days_list = []

    current = start
    while current <= today:
        day_key = current.isoformat()
        day_data = daily.get(day_key, {"count": 0, "bonus_count": 0})

        # Calculate allowance for this day
        day_dt = datetime.combine(current, datetime.min.time(), tzinfo=TZ)
        allowance = engine.daily_allowance(day_dt)

        days_list.append({
            "date": day_key,
            "count": day_data["count"],
            "bonus_count": day_data["bonus_count"],
            "allowance": allowance,
        })
        current += timedelta(days=1)

    return {"days": days_list}


@router.get("/api/history/entries", response_model=list[HistoryEntry])
async def get_history_entries():
    """Return raw entry list (for debugging/export)."""
    engine = _get_engine()
    entries = entry_store.load()
    result = []
    for e in entries:
        ts_aware = e.timestamp.astimezone(TZ) if e.timestamp.tzinfo else e.timestamp.replace(tzinfo=TZ)
        week_idx = engine.current_week_index(ts_aware)
        result.append(
            HistoryEntry(
                id=e.id,
                timestamp=e.timestamp,
                is_bonus=e.is_bonus,
                week_index=week_idx,
            )
        )
    return result


@router.get("/api/progress")
async def get_progress():
    """Return comprehensive progress/savings data for charting."""
    engine = _get_engine()
    config = config_store.load()
    entries = entry_store.load()
    now = _now()
    today = now.date()

    # --- Aggregate entries by date ---
    daily_counts: dict[date, int] = defaultdict(int)
    for e in entries:
        ts = e.timestamp.astimezone(TZ) if e.timestamp.tzinfo else e.timestamp.replace(tzinfo=TZ)
        daily_counts[ts.date()] += 1

    # --- Build cumulative arrays ---
    cumulative_avoided = []
    cumulative_saved = []
    total_smoked_so_far = 0
    baseline = config.baseline_daily_count
    cost = config.cost_per_cigarette

    current = config.start_date
    while current <= today:
        smoked_that_day = daily_counts.get(current, 0)
        total_smoked_so_far += smoked_that_day
        days_elapsed = (current - config.start_date).days + 1
        would_have_smoked = days_elapsed * baseline
        avoided = max(0, would_have_smoked - total_smoked_so_far)
        saved = avoided * cost

        cumulative_avoided.append({
            "date": current.isoformat(),
            "avoided_cumulative": avoided,
        })
        cumulative_saved.append({
            "date": current.isoformat(),
            "saved_cumulative": round(saved, 2),
        })
        current += timedelta(days=1)

    # --- Current totals ---
    total_smoked = len(entries)
    current_avoided = engine.cigarettes_avoided(total_smoked, now)
    current_saved = engine.money_saved(total_smoked, now)

    # --- Projections ---
    quit_dt = engine.quit_date()
    total_days_program = (quit_dt - config.start_date).days
    # Project assuming current avg smoking rate continues
    days_so_far = max(1, engine.days_since_start(now))
    avg_daily_smoked = total_smoked / days_so_far
    days_remaining = max(0, (quit_dt - today).days)
    projected_total_smoked = total_smoked + int(avg_daily_smoked * days_remaining)
    projected_would_have = total_days_program * baseline
    projected_total_avoided = max(0, projected_would_have - projected_total_smoked)
    projected_total_saved = round(projected_total_avoided * cost, 2)

    projections = {
        "quit_date": quit_dt.isoformat(),
        "projected_total_avoided": projected_total_avoided,
        "projected_total_saved": projected_total_saved,
    }

    # --- Milestones ---
    milestones = []

    # Avoided milestones
    for target in MILESTONES_AVOIDED:
        reached = current_avoided >= target
        reached_date = None
        if reached:
            # Find the date it was reached
            running_smoked = 0
            d = config.start_date
            while d <= today:
                running_smoked += daily_counts.get(d, 0)
                days_el = (d - config.start_date).days + 1
                would = days_el * baseline
                if would - running_smoked >= target:
                    reached_date = d.isoformat()
                    break
                d += timedelta(days=1)
        milestones.append({
            "name": f"{target} avoided",
            "reached": reached,
            "date": reached_date,
        })

    # Saved milestones
    for target in MILESTONES_SAVED:
        reached = current_saved >= target
        reached_date = None
        if reached:
            running_smoked = 0
            d = config.start_date
            while d <= today:
                running_smoked += daily_counts.get(d, 0)
                days_el = (d - config.start_date).days + 1
                would = days_el * baseline
                av = would - running_smoked
                if av * cost >= target:
                    reached_date = d.isoformat()
                    break
                d += timedelta(days=1)
        milestones.append({
            "name": f"€{target} saved",
            "reached": reached,
            "date": reached_date,
        })

    # --- Fun equivalents ---
    fun_equivalents = []
    for name, unit_cost in FUN_EQUIVALENTS:
        count = int(current_saved / unit_cost)
        if count > 0:
            fun_equivalents.append({
                "amount": round(current_saved, 2),
                "equivalent": f"That's {count} {name}",
            })

    # --- Weekly comparison ---
    weekly_comparison = []
    num_weeks = min(
        len(config.weekly_schedules),
        (today - config.start_date).days // 7 + 1,
    )
    for week_idx in range(num_weeks):
        week_start_date = config.start_date + timedelta(weeks=week_idx)
        week_end_date = week_start_date + timedelta(days=7)

        week_smoked = 0
        d = week_start_date
        while d < week_end_date and d <= today:
            week_smoked += daily_counts.get(d, 0)
            d += timedelta(days=1)

        # Allowance for the week
        week_dt = datetime.combine(week_start_date, time.min, tzinfo=TZ)
        daily_allow = engine.daily_allowance(week_dt)
        days_in_week = min(7, (today - week_start_date).days + 1) if week_end_date > today else 7
        week_allowance = daily_allow * days_in_week

        # Baseline for the week
        week_baseline = baseline * days_in_week
        saved_vs_baseline = (week_baseline - week_smoked) * cost

        weekly_comparison.append({
            "week": week_idx + 1,
            "smoked": week_smoked,
            "allowance": week_allowance,
            "saved_vs_baseline": round(saved_vs_baseline, 2),
        })

    return {
        "cumulative_avoided": cumulative_avoided,
        "cumulative_saved": cumulative_saved,
        "projections": projections,
        "milestones": milestones,
        "fun_equivalents": fun_equivalents,
        "weekly_comparison": weekly_comparison,
    }


@router.get("/api/report/weekly")
async def get_weekly_report():
    """Detailed weekly report card with insights."""
    engine = _get_engine()
    config = config_store.load()
    entries = entry_store.load()
    now = _now()

    # Current week boundaries
    week_start = engine.current_week_start(now)
    week_end = week_start + timedelta(days=7)
    today = now.date()

    # Previous week boundaries
    prev_week_start = week_start - timedelta(weeks=1)
    prev_week_end = week_start

    # Entries for current and previous week
    this_week_entries = [
        e for e in entries
        if week_start <= e.timestamp.astimezone(TZ) < week_end
    ]
    prev_week_entries = [
        e for e in entries
        if prev_week_start <= e.timestamp.astimezone(TZ) < prev_week_end
    ]

    # --- Daily breakdown for this week ---
    daily_breakdown = []
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    best_day = None
    best_day_count = float('inf')
    worst_day = None
    worst_day_count = -1

    for i in range(7):
        day_date = (week_start + timedelta(days=i)).date()
        if day_date > today:
            break

        day_entries = [
            e for e in this_week_entries
            if e.timestamp.astimezone(TZ).date() == day_date
        ]
        regular = len([e for e in day_entries if not e.is_bonus])
        bonus = len([e for e in day_entries if e.is_bonus])
        day_dt = datetime.combine(day_date, datetime.min.time(), tzinfo=TZ)
        allowance = engine.daily_allowance(day_dt)
        under_budget = allowance - regular

        daily_breakdown.append({
            "date": day_date.isoformat(),
            "day_name": day_names[i],
            "smoked": regular,
            "bonus": bonus,
            "allowance": allowance,
            "under_budget": under_budget,
        })

        if regular < best_day_count:
            best_day_count = regular
            best_day = day_names[i]
        if regular > worst_day_count:
            worst_day_count = regular
            worst_day = day_names[i]

    # --- Totals ---
    this_week_regular = len([e for e in this_week_entries if not e.is_bonus])
    this_week_bonus = len([e for e in this_week_entries if e.is_bonus])
    prev_week_regular = len([e for e in prev_week_entries if not e.is_bonus])

    # Days elapsed this week
    days_elapsed = min(7, (today - week_start.date()).days + 1)
    days_elapsed_prev = 7

    # Daily averages
    avg_this_week = round(this_week_regular / days_elapsed, 1) if days_elapsed > 0 else 0
    avg_prev_week = round(prev_week_regular / days_elapsed_prev, 1) if days_elapsed_prev > 0 else 0
    trend = round(avg_this_week - avg_prev_week, 1)

    # --- Longest gap between cigarettes this week ---
    week_non_bonus = sorted(
        [e for e in this_week_entries if not e.is_bonus],
        key=lambda e: e.timestamp,
    )
    longest_gap_hours = 0.0
    if len(week_non_bonus) >= 2:
        for j in range(1, len(week_non_bonus)):
            gap = (week_non_bonus[j].timestamp.astimezone(TZ) - week_non_bonus[j-1].timestamp.astimezone(TZ)).total_seconds() / 3600
            if gap > longest_gap_hours:
                longest_gap_hours = gap
    elif len(week_non_bonus) == 1:
        # Gap from start of week to first entry, or from last entry to now
        gap_to_now = (now - week_non_bonus[0].timestamp.astimezone(TZ)).total_seconds() / 3600
        gap_from_start = (week_non_bonus[0].timestamp.astimezone(TZ) - week_start).total_seconds() / 3600
        longest_gap_hours = max(gap_to_now, gap_from_start)

    # --- Week allowance total ---
    week_allowance_total = engine.daily_allowance(now) * days_elapsed
    total_under_budget = week_allowance_total - this_week_regular

    # --- Achievements ---
    achievements = []
    if total_under_budget > 0:
        achievements.append(f"🏆 {total_under_budget} under budget this week")
    if best_day_count == 0 and days_elapsed > 0:
        achievements.append(f"⭐ Zero-cigarette day: {best_day}!")
    if longest_gap_hours >= 12:
        achievements.append(f"⏱️ Longest gap: {longest_gap_hours:.1f}h — great restraint!")
    if trend < 0:
        achievements.append(f"📉 Averaging {abs(trend):.1f} fewer/day than last week")
    if this_week_bonus == 0 and days_elapsed >= 3:
        achievements.append("🎁 No bonus used this week (so far)")

    # --- Comparison to previous week ---
    comparison = {
        "this_week_total": this_week_regular,
        "prev_week_total": prev_week_regular,
        "difference": this_week_regular - prev_week_regular,
        "this_week_avg": avg_this_week,
        "prev_week_avg": avg_prev_week,
        "trend": "improving" if trend < 0 else "same" if trend == 0 else "higher",
    }

    # --- Grade ---
    if days_elapsed >= 1:
        compliance = total_under_budget / (week_allowance_total or 1)
        if compliance >= 0.2:
            grade = "A"
        elif compliance >= 0:
            grade = "B"
        elif compliance >= -0.1:
            grade = "C"
        else:
            grade = "D"
    else:
        grade = "—"

    return {
        "week_index": engine.current_week_index(now) + 1,
        "week_start": week_start.date().isoformat(),
        "days_elapsed": days_elapsed,
        "grade": grade,
        "daily_breakdown": daily_breakdown,
        "totals": {
            "smoked": this_week_regular,
            "bonus_used": this_week_bonus,
            "allowance": week_allowance_total,
            "under_budget": total_under_budget,
        },
        "longest_gap_hours": round(longest_gap_hours, 1),
        "best_day": best_day,
        "worst_day": worst_day,
        "avg_per_day": avg_this_week,
        "comparison": comparison,
        "achievements": achievements,
    }
