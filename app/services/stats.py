"""Training streak and weekly stats."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session
from syncfit_database import Profile, SessionRecord, User

DEFAULT_WEEKLY_GOAL = 4
DEFAULT_REST_ALLOWANCE = 3


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def compute_stats(session: Session, user: User, profile: Profile | None, today: date | None = None) -> dict:
    today = today or _utc_today()
    records = session.query(SessionRecord).filter_by(user_id=user.id).all()
    training_dates = {record.started_at.date() for record in records}

    goal = (profile.weekly_training_goal if profile else None) or DEFAULT_WEEKLY_GOAL
    allowance = (profile.rest_days_allowance if profile else None)
    if allowance is None:
        allowance = DEFAULT_REST_ALLOWANCE

    monday = today - timedelta(days=today.weekday())
    week_training = sum(1 for d in training_dates if monday <= d <= today)

    # Streak: walk back from today; each untrained day consumes a weekly wildcard.
    rest_used: dict[tuple[int, int], int] = defaultdict(int)
    streak = 0
    cursor = today
    guard = 0
    while guard < 400:
        guard += 1
        if cursor in training_dates:
            streak += 1
        else:
            iso = cursor.isocalendar()
            key = (iso.year, iso.week)
            if cursor != today and rest_used[key] < allowance:
                rest_used[key] += 1
            elif cursor == today:
                pass  # today may still be trained
            else:
                break
        cursor -= timedelta(days=1)

    current_iso = today.isocalendar()
    rest_left_this_week = max(allowance - rest_used[(current_iso.year, current_iso.week)], 0)

    return {
        "streak_days": streak,
        "today_trained": today in training_dates,
        "week_training_days": week_training,
        "weekly_goal": goal,
        "rest_days_allowance": allowance,
        "rest_days_left": rest_left_this_week,
        "training_dates": sorted(d.isoformat() for d in training_dates),
    }


__all__ = ["compute_stats"]
