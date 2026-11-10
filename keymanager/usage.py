from bisect import bisect_right
from datetime import datetime, timedelta


def _add_months(moment, months):
    total = moment.year * 12 + (moment.month - 1) + months
    return moment.replace(year=total // 12, month=total % 12 + 1, day=1)


def scope_edges(now):
    hour = now.replace(minute=0, second=0, microsecond=0)
    month = hour.replace(day=1, hour=0)
    return {
        'day': [hour - timedelta(hours=23 - i) for i in range(25)],
        'year': [_add_months(month, i - 11) for i in range(13)],
    }


def month_edges(now):
    month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    months = []
    for back in range(11, -1, -1):
        first = _add_months(month, -back)
        length = (_add_months(first, 1) - first).days
        months.append([first + timedelta(days=offset) for offset in range(length + 1)])
    return months


def bucket_counts(moments, edges):
    counts = [0] * (len(edges) - 1)
    for moment in moments:
        index = bisect_right(edges, moment) - 1
        if 0 <= index < len(counts):
            counts[index] += 1
    return counts


def usage_series(moments_by_key, now=None):
    now = now or datetime.now()
    edges = scope_edges(now)
    months = month_edges(now)
    result = {}
    for key_id, moments in moments_by_key.items():
        series = {
            scope: {
                'edges': [int(edge.timestamp() * 1000) for edge in scope_edge],
                'counts': bucket_counts(moments, scope_edge),
            }
            for scope, scope_edge in edges.items()
        }
        series['months'] = [
            {
                'edges': [int(edge.timestamp() * 1000) for edge in month_edge],
                'counts': bucket_counts(moments, month_edge),
            }
            for month_edge in months
        ]
        result[key_id] = series
    return result
