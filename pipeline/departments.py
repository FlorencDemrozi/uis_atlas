"""Map Scopus affiliation text to UiS departments, aware of renames and splits.

Used by collect_scopus.py and build_profiles.py. Pure functions, so they can be
tested without Scopus data.
"""
from collections import Counter

from config import (DEPARTMENT_HISTORY, DEPARTMENTS, EXCLUDED_UNIT_PHRASES, FACULTY_HINTS,
                    NOT_STATED_KEYS, not_stated)

RECENT_WINDOW = 1   # years before a person's latest affiliation that still count as "current"


def match_dept(org_strings: list[str], year: int | None = None) -> str | None:
    """Department named in one paper's affiliation text; a faculty's "not stated"
    key if only the faculty is recognisable (including split former departments);
    None for other or excluded units."""
    text = " ".join(org_strings).lower()
    for h in DEPARTMENT_HISTORY:
        if h.get("until") and year and year > h["until"]:
            continue
        if any(p in text for p in h["phrases"]):
            return h["became"] or not_stated(h["faculty"])
    for dept, keys in DEPARTMENTS:
        if any(k in text for k in keys):
            return dept
    if any(p in text for p in EXCLUDED_UNIT_PHRASES):
        return None
    for faculty, hints in FACULTY_HINTS:
        if any(h in text for h in hints):
            return not_stated(faculty)
    return None


def current_department(observations: list[tuple[int | None, str | None]]) -> str | None:
    """Pick a person's department from (year, matched department) observations.

    The most recent affiliation wins, so people from split or renamed departments
    get today's department. Within the latest years, the most frequent department
    wins (ties: most frequent overall). A "not stated" key only if nothing better
    is known (then the most recent faculty).
    """
    seen = [(y or 0, d) for y, d in observations if d]
    real = [(y, d) for y, d in seen if d not in NOT_STATED_KEYS]
    pool = real or seen
    if not pool:
        return None
    latest = max(y for y, _ in pool)
    recent = Counter(d for y, d in pool if y >= latest - RECENT_WINDOW)
    overall = Counter(d for _, d in pool)
    return max(recent, key=lambda d: (recent[d], overall[d]))
