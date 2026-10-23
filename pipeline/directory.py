"""Match Scopus authors to the UiS employee directory (from collect_directory.py).

Used by build_profiles.py. Pure functions, so they can be tested without data.

Match strength:
  3  same full name (accent- and punctuation-insensitive)
  2  same surname and first given name
  1  same surname and initial, or the Scopus given name is a middle name
Weak (1) matches, and ties, only count when the Scopus department is in the
same faculty as the directory unit.
"""
import re
import unicodedata
from collections import defaultdict

from config import (DIRECTORY_DEPARTMENTS, DIRECTORY_EXCLUDED_UNITS, DIRECTORY_FACULTIES,
                    FACULTY_OF)

TRANSLIT = str.maketrans({"ø": "o", "æ": "ae", "ð": "d", "þ": "th", "ß": "ss", "ł": "l", "đ": "d"})


def tokens(name: str) -> list[str]:
    text = unicodedata.normalize("NFKD", (name or "").lower().translate(TRANSLIT))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return [t for t in re.split(r"[^a-z0-9]+", text) if t]


def name_score(surname: str, given: str, full_name: str) -> int:
    s, g, d = tokens(surname), tokens(given), tokens(full_name)
    if not s or not g or not d or d[-1] not in s:
        return 0
    rest = [t for t in d if t not in s]         # directory given and middle names
    if not rest:
        return 0
    missing_surname = any(t not in d for t in s)  # e.g. Scopus has a second surname
    if len(g[0]) == 1:
        score = 1 if rest[0].startswith(g[0]) else 0
    elif g[0] == rest[0]:
        score = 3 if sorted(s + g) == sorted(d) else 2
    elif g[0] in rest:
        score = 1
    else:
        return 0
    return max(1, score - 1) if missing_surname and score else score


def describe(entry: dict, units: dict) -> dict:
    """Atlas placement of one directory entry: departments, faculty, or excluded."""
    ids = [int(u) for u in entry["units"]]
    depts = [DIRECTORY_DEPARTMENTS[u] for u in ids if u in DIRECTORY_DEPARTMENTS]
    if depts:
        return {"departments": depts, "faculty": FACULTY_OF[depts[0]], "excluded": False}
    if any(u in DIRECTORY_EXCLUDED_UNITS for u in ids):
        return {"departments": [], "faculty": None, "excluded": True}
    for u in ids:
        parent = units.get(str(u), {}).get("parent")
        faculty = DIRECTORY_FACULTIES.get(u) or DIRECTORY_FACULTIES.get(int(parent or 0))
        if faculty:   # e.g. faculty administration: faculty known, department not
            return {"departments": [], "faculty": faculty, "excluded": False}
    return {"departments": [], "faculty": None, "excluded": True}   # outside the faculties


class Directory:
    def __init__(self, data: dict | None):
        data = data or {"employees": [], "units": {}}
        self.entries = []
        self.by_surname = defaultdict(list)
        for i, e in enumerate(data["employees"]):
            entry = dict(e, id=i, **describe(e, data["units"]))
            self.entries.append(entry)
            toks = tokens(e["name"])
            if toks:
                self.by_surname[toks[-1]].append(entry)

    def match(self, surname: str, given: str, scopus_dept: str | None) -> tuple[dict | None, int]:
        """Best directory entry for one Scopus author, with its strength (0 = none)."""
        pool = {e["id"]: e for t in tokens(surname) for e in self.by_surname.get(t, [])}
        scored = [(name_score(surname, given, e["name"]), e) for e in pool.values()]
        scored = [(s, e) for s, e in scored if s]
        if not scored:
            return None, 0
        best = max(s for s, _ in scored)
        top = [e for s, e in scored if s == best]
        faculty = FACULTY_OF.get(scopus_dept or "")
        same_faculty = [e for e in top if faculty and e["faculty"] == faculty]
        if len(top) == 1 and (best >= 2 or same_faculty):
            return top[0], best
        if len(same_faculty) == 1:
            return same_faculty[0], best
        return None, 0
