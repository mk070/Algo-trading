from __future__ import annotations

from statistics import median
from typing import Iterable, Optional


def lead_time_summary(session_dates: Iterable[str], breakouts: Iterable[str], first_flags: Iterable[Optional[str]]) -> dict:
    """Summarize scanner lead sessions for aligned breakout and first-flag dates."""
    sessions = sorted(set(session_dates))
    position = {date: i for i, date in enumerate(sessions)}
    events = list(zip(breakouts, first_flags))
    leads = []
    before = after = never = 0
    for breakout, flag in events:
        if flag is None or breakout not in position or flag not in position:
            never += 1
            continue
        lead = position[breakout] - position[flag]
        leads.append(lead)
        if lead > 0:
            before += 1
        else:
            after += 1
    total = len(events)
    return {
        "breakout_count": total,
        "median_sessions_earlier": median(leads) if leads else None,
        "flagged_before_pct": round(100 * before / total, 1) if total else None,
        "flagged_on_or_after_pct": round(100 * after / total, 1) if total else None,
        "never_flagged_pct": round(100 * never / total, 1) if total else None,
        "before_count": before,
        "on_or_after_count": after,
        "never_count": never,
    }
