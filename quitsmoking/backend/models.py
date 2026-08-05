"""Pydantic models for the QuitSmoking API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CigaretteEntry(BaseModel):
    id: UUID
    timestamp: datetime
    is_bonus: bool = False


class LogRequest(BaseModel):
    is_bonus: bool = False
    timestamp: Optional[datetime] = None  # Override to log for a past date/time


class WeekScheduleModel(BaseModel):
    mode: str  # "daily", "interval", "quit"
    allowance: int = 0
    interval_hours: float = 0.0


class ConfigUpdate(BaseModel):
    start_date: Optional[date] = None
    weekly_schedules: Optional[list[WeekScheduleModel]] = None
    bonus_per_week: Optional[int] = None
    cost_per_cigarette: Optional[float] = None
    baseline_daily_count: Optional[int] = None
    smoking_window_start_minutes: Optional[int] = None
    smoking_window_end_minutes: Optional[int] = None


class StatusResponse(BaseModel):
    # Current schedule info
    week_index: int
    week_start: datetime
    mode: str  # "daily", "interval", "quit"
    daily_allowance: int
    bonus_allowance: int
    interval_hours: Optional[float] = None

    # Today's state
    smoked_today: int
    bonus_used_this_week: int
    remaining_today: int
    remaining_bonus: int

    # Timing
    can_smoke: bool
    time_until_next_seconds: float
    next_allowed_time: Optional[datetime] = None
    schedule_times: list[tuple[int, int]] = Field(default_factory=list)

    # Progress
    days_since_start: int
    days_until_quit: int
    quit_date: date
    total_smoked: int
    cigarettes_avoided: int
    money_saved: float


class HistoryEntry(BaseModel):
    id: UUID
    timestamp: datetime
    is_bonus: bool
    week_index: int
