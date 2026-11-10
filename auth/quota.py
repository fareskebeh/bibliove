import calendar
from datetime import datetime


def _anchor_in(year, month, created):
    day = min(created.day, calendar.monthrange(year, month)[1])
    return datetime(year, month, day, created.hour, created.minute, created.second)


def last_reset_point(created, now):
    anchor = _anchor_in(now.year, now.month, created)
    if anchor > now:
        previous = now.month - 1 or 12
        year = now.year if now.month > 1 else now.year - 1
        anchor = _anchor_in(year, previous, created)
    return anchor


def apply_quota_reset(user, now=None):
    now = now or datetime.now()
    created = user.date_created or now
    point = last_reset_point(created, now)
    if user.quota_reset_at is None or user.quota_reset_at < point:
        user.master_quota = 0
        user.quota_reset_at = point
        return True
    return False
