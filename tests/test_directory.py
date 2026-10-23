"""Matching Scopus authors to the UiS employee directory (synthetic data only)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
from build_profiles import build  # noqa: E402
from directory import Directory, name_score  # noqa: E402

MATH = "Mathematics and Physics"
PSY = "Department of Psychology"
UNITS = {"1222": {"parent": None}, "1259": {"parent": "1222"}, "1253": {"parent": "1222"},
         "1241": {"parent": None}, "8977": {"parent": "1241"}, "1226": {"parent": "1224"},
         "1224": {"parent": None}}


def emp(name, *units, pos="Professor"):
    return {"name": name, "units": list(units), "position_nb": pos, "position_en": pos,
            "url_nb": f"https://www.uis.no/nb/profile/{name.lower().replace(' ', '-')}"}


def test_name_scores():
    assert name_score("Nordmann", "Kari", "Kari Nordmann") == 3
    assert name_score("Nordmann", "Kari", "Kari Anne Nordmann") == 2
    assert name_score("Nordmann", "K.", "Kari Nordmann") == 1
    assert name_score("Øvrebø", "Åse", "Ase Ovrebo") == 3
    assert name_score("Hjelmeland Larsen", "Per", "Per Larsen") == 1   # extra surname
    assert name_score("Nordmann", "Ola", "Kari Nordmann") == 0
    assert name_score("Hansen", "Kari", "Kari Nordmann") == 0


def test_weak_or_tied_matches_need_the_same_faculty():
    d = Directory({"units": UNITS, "employees": [emp("Kari Nordmann", "1259"),
                                                   emp("Kristin Nordmann", "8977")]})
    assert d.match("Nordmann", "K.", None) == (None, 0)                # two candidates
    entry, score = d.match("Nordmann", "K.", MATH)
    assert entry["name"] == "Kari Nordmann" and score == 1
    assert d.match("Nordmann", "Kari", None)[0]["departments"] == [MATH]


def test_directory_sets_department_threshold_and_exclusion():
    papers = {"p1": {"title": "t", "year": "2024", "citations": 0, "keywords": [], "coauthor_ids": ["a"]},
              "p2": {"title": "t", "year": "2025", "citations": 0, "keywords": [], "coauthor_ids": ["b"]},
              "p3": {"title": "t", "year": "2025", "citations": 0, "keywords": [], "coauthor_ids": ["c"]},
              "p4": {"title": "t", "year": "2025", "citations": 0, "keywords": [], "coauthor_ids": ["d"]}}
    authors = [
        {"scopus_id": "a", "name": "Kari Nordmann", "department": None, "papers": ["p1"]},
        {"scopus_id": "b", "name": "Ola Hansen", "department": MATH, "papers": ["p2"]},
        {"scopus_id": "c", "name": "Liv Berg", "department": None, "papers": ["p3"]},
        {"scopus_id": "d", "name": "Per Dahl", "department": MATH, "papers": ["p4"]},
    ]
    d = Directory({"units": UNITS, "employees": [
        emp("Kari Nordmann", "8977"), emp("Liv Berg", "1226"), emp("Per Dahl", "1253")]})
    res = build({"authors": authors, "papers": papers}, {}, {}, reference_year=2026,
                recent_years=3, min_recent=1, directory=d, unconfirmed_years=2, unconfirmed_min=3)
    a, b, c, dd = (res["people"][k] for k in "abcd")
    assert (a["department"], a["faculty"], a["included"]) == (PSY, "Faculty of Social Sciences", True)
    assert a["position"]["nb"] == "Professor" and a["uis_links"]["nb"].endswith("kari-nordmann")
    assert (b["department"], b["included"]) == (MATH, False)           # not in directory: strict rule
    assert c["included"] is False                                      # only in an excluded centre
    assert (dd["department"], dd["included"]) == (MATH, True)          # faculty admin + Scopus dept
