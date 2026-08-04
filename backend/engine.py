"""Schedule engine — Python port of the Swift ScheduleEngine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum, auto
from typing import Optional

from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Amsterdam")


# ---------------------------------------------------------------------------
# WeekSchedule
# ---------------------------------------------------------------------------

class ScheduleMode(Enum):
    DAILY = auto()
    INTERVAL = auto()
    QUIT = auto()


@dataclass(frozen=True)
class WeekSchedule:
    mode: ScheduleMode
    allowance: int = 0
    interval_hours: float = 0.0

    @staticmethod
    def daily(allowance: int) -> "WeekSchedule":
        return WeekSchedule(mode=ScheduleMode.DAILY, allowance=allowance)

    @staticmethod
    def interval(hours: float) -> "WeekSchedule":
        return WeekSchedule(mode=ScheduleMode.INTERVAL, interval_hours=hours)

    @staticmethod
    def quit() -> "WeekSchedule":
        return WeekSchedule(mode=ScheduleMode.QUIT)


# ---------------------------------------------------------------------------
# ScheduleConfig
# ---------------------------------------------------------------------------

@dataclass
class ScheduleConfig:
    start_date: date
    weekly_schedules: list[WeekSchedule]
    bonus_per_week: int = 1
    cost_per_cigarette: float = 0.565
    baseline_daily_count: int = 20
    smoking_window_start_minutes: int = 450   # 07:30
    smoking_window_end_minutes: int = 1350    # 22:30


def default_config() -> ScheduleConfig:
    return ScheduleConfig(
        start_date=date(2026, 6, 15),
        weekly_schedules=[
            WeekSchedule.daily(8),
            WeekSchedule.daily(7),
            WeekSchedule.daily(6),
            WeekSchedule.daily(5),
            WeekSchedule.daily(4),
            WeekSchedule.daily(3),
            WeekSchedule.daily(2),
            WeekSchedule.interval(12),
            WeekSchedule.interval(14),
            WeekSchedule.quit(),
        ],
        bonus_per_week=1,
        cost_per_cigarette=0.565,
        baseline_daily_count=20,
        smoking_window_start_minutes=450,
        smoking_window_end_minutes=1350,
    )


# ---------------------------------------------------------------------------
# ScheduleEngine
# ---------------------------------------------------------------------------

class ScheduleEngine:
    def __init__(self, config: Optional[ScheduleConfig] = None):
        self.config = config or default_config()

    def _now(self, now: Optional[datetime] = None) -> datetime:
        return now if now is not None else datetime.now(TZ)

    # -- week calculations --

    def current_week_index(self, now: Optional[datetime] = None) -> int:
        now = self._now(now)
        delta = now.date() - self.config.start_date
        idx = delta.days // 7
        return max(0, min(idx, len(self.config.weekly_schedules) - 1))

    def current_week_start(self, now: Optional[datetime] = None) -> datetime:
        now = self._now(now)
        idx = self.current_week_index(now)
        week_start_date = self.config.start_date + timedelta(weeks=idx)
        return datetime.combine(week_start_date, datetime.min.time(), tzinfo=TZ)

    def current_week_schedule(self, now: Optional[datetime] = None) -> WeekSchedule:
        return self.config.weekly_schedules[self.current_week_index(now)]

    # -- mode queries --

    def is_interval_mode(self, now: Optional[datetime] = None) -> bool:
        return self.current_week_schedule(now).mode == ScheduleMode.INTERVAL

    def current_interval(self, now: Optional[datetime] = None) -> Optional[float]:
        schedule = self.current_week_schedule(now)
        if schedule.mode == ScheduleMode.INTERVAL:
            return schedule.interval_hours
        return None

    def daily_allowance(self, now: Optional[datetime] = None) -> int:
        schedule = self.current_week_schedule(now)
        if schedule.mode == ScheduleMode.DAILY:
            return schedule.allowance
        if schedule.mode == ScheduleMode.INTERVAL:
            window_minutes = (
                self.config.smoking_window_end_minutes
                - self.config.smoking_window_start_minutes
            )
            window_hours = window_minutes / 60.0
            return max(1, int(window_hours / schedule.interval_hours) + 1)
        return 0

    def bonus_allowance(self, now: Optional[datetime] = None) -> int:
        schedule = self.current_week_schedule(now)
        if schedule.mode == ScheduleMode.QUIT:
            return 0
        return self.config.bonus_per_week

    # -- timing --

    def next_allowed_time(
        self, last_entry: Optional[datetime], now: Optional[datetime] = None
    ) -> Optional[datetime]:
        now = self._now(now)
        schedule = self.current_week_schedule(now)

        if schedule.mode == ScheduleMode.QUIT:
            return None

        if schedule.mode == ScheduleMode.DAILY:
            return None

        # Interval mode
        if last_entry is None:
            today_start = now.replace(
                hour=self.config.smoking_window_start_minutes // 60,
                minute=self.config.smoking_window_start_minutes % 60,
                second=0,
                microsecond=0,
            )
            return today_start if now < today_start else now

        next_time = last_entry + timedelta(hours=schedule.interval_hours)

        window_start_today = now.replace(
            hour=self.config.smoking_window_start_minutes // 60,
            minute=self.config.smoking_window_start_minutes % 60,
            second=0,
            microsecond=0,
        )
        window_end_today = now.replace(
            hour=self.config.smoking_window_end_minutes // 60,
            minute=self.config.smoking_window_end_minutes % 60,
            second=0,
            microsecond=0,
        )

        if next_time < window_start_today:
            return window_start_today
        if next_time > window_end_today:
            tomorrow_start = window_start_today + timedelta(days=1)
            return tomorrow_start

        return next_time

    def can_smoke_now(
        self, last_entry: Optional[datetime], now: Optional[datetime] = None
    ) -> bool:
        now = self._now(now)
        schedule = self.current_week_schedule(now)

        if schedule.mode == ScheduleMode.QUIT:
            return False
        if schedule.mode == ScheduleMode.DAILY:
            return True

        next_time = self.next_allowed_time(last_entry, now)
        if next_time is None:
            return False
        return now >= next_time

    def time_until_next(
        self, last_entry: Optional[datetime], now: Optional[datetime] = None
    ) -> float:
        """Seconds until next allowed smoke. Returns 0 if allowed now."""
        now = self._now(now)
        if self.can_smoke_now(last_entry, now):
            return 0.0
        next_time = self.next_allowed_time(last_entry, now)
        if next_time is None:
            return 0.0
        diff = (next_time - now).total_seconds()
        return max(0.0, diff)

    # -- progress --

    def quit_date(self) -> date:
        weeks = len(self.config.weekly_schedules)
        return self.config.start_date + timedelta(weeks=weeks)

    def days_until_quit(self, now: Optional[datetime] = None) -> int:
        now = self._now(now)
        delta = self.quit_date() - now.date()
        return max(0, delta.days)

    def days_since_start(self, now: Optional[datetime] = None) -> int:
        now = self._now(now)
        delta = now.date() - self.config.start_date
        return max(0, delta.days)

    def cigarettes_avoided(self, total_smoked: int, now: Optional[datetime] = None) -> int:
        now = self._now(now)
        days = self.days_since_start(now)
        would_have_smoked = days * self.config.baseline_daily_count
        return max(0, would_have_smoked - total_smoked)

    def money_saved(self, total_smoked: int, now: Optional[datetime] = None) -> float:
        avoided = self.cigarettes_avoided(total_smoked, now)
        return avoided * self.config.cost_per_cigarette

    # -- schedule times --

    def smoking_schedule_times(
        self, now: Optional[datetime] = None
    ) -> list[tuple[int, int]]:
        """Return evenly-spaced (hour, minute) tuples for the day's allowance."""
        now = self._now(now)
        allowance = self.daily_allowance(now)
        if allowance <= 0:
            return []

        window_start = self.config.smoking_window_start_minutes
        window_end = self.config.smoking_window_end_minutes
        window_duration = window_end - window_start

        if allowance == 1:
            mid = window_start + window_duration // 2
            return [(mid // 60, mid % 60)]

        interval = window_duration / (allowance - 1)
        times: list[tuple[int, int]] = []
        for i in range(allowance):
            minutes = int(window_start + i * interval)
            times.append((minutes // 60, minutes % 60))
        return times
