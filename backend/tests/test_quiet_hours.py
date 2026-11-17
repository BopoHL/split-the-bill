"""The do-not-disturb night the bot's own messages wait out."""
from datetime import datetime

from app.utils import quiet_hours


def test_quiet_hours_defer_without_burning_a_step(monkeypatch):
    """Waiting out the night must not push everyone onto the slowest cadence."""
    monkeypatch.setenv("REMINDER_TZ", "UTC")
    monkeypatch.setenv("REMINDER_QUIET_HOURS", "23:00-09:00")

    night = datetime(2026, 8, 11, 2, 30)
    assert quiet_hours.in_quiet_hours(night) is True

    resumed = quiet_hours.next_allowed_moment(night)
    assert resumed.hour == 9 and resumed.day == night.day

    day = datetime(2026, 8, 11, 14, 0)
    assert quiet_hours.in_quiet_hours(day) is False
    assert quiet_hours.next_allowed_moment(day) == day


def test_quiet_window_wraps_past_midnight(monkeypatch):
    monkeypatch.setenv("REMINDER_TZ", "UTC")
    monkeypatch.setenv("REMINDER_QUIET_HOURS", "23:00-09:00")

    assert quiet_hours.in_quiet_hours(datetime(2026, 8, 11, 23, 30)) is True
    # 23:30 defers to 09:00 the NEXT morning, not the one that already passed.
    resumed = quiet_hours.next_allowed_moment(datetime(2026, 8, 11, 23, 30))
    assert resumed.day == 12 and resumed.hour == 9
