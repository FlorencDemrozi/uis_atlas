"""Map Scopus affiliation text to faculty departments, aware of renames and splits.

Used by collect_scopus.py. Pure functions, so they can be tested without Scopus data.
"""
from collections import Counter

from config import DEPARTMENT_HISTORY, DEPARTMENTS, FACULTY_HINTS, NOT_STATED

RECENT_WINDOW = 1   # years before a person's latest affiliation that still count as "current"


def match_dept(org_strings: list[str], year: int | None = None) -> str | None:
    """Department named in one paper's affiliation text, NOT_STATED if only the
    faculty is recognisable (including split former departments), else None."""
    text = " ".join(org_strings).lower()
    for h in DEPARTMENT_HISTORY:
        if h.get("until") and year and year > h["until"]:
            continue
        if any(p in text for p in h["phrases"]):
            return h["became"] or NOT_STATED
    for dept, keys in DEPARTMENTS:
        if any(k in text for k in keys):
            return dept
    if any(h in text for h in FACULTY_HINTS):
        return NOT_STATED
    return None


def current_department(observations: list[tuple[int | None, str | None]]) -> str | None:
    """Pick a person's department from (year, matched department) observations.

    The most recent affiliation wins, so people from split or renamed departments
    get today's department. Within the latest years, the most frequent department
    wins (ties: most frequent overall). NOT_STATED only if nothing better is known.
    """
    real = [(y or 0, d) for y, d in observations if d and d != NOT_STATED]
    if not real:
        return NOT_STATED if any(d == NOT_STATED for _, d in observations) else None
    latest = max(y for y, _ in real)
    recent = Counter(d for y, d in real if y >= latest - RECENT_WINDOW)
    overall = Counter(d for _, d in real)
    return max(recent, key=lambda d: (recent[d], overall[d]))
