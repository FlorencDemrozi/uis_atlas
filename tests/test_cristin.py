"""Staff status from Cristin person records (collect_cristin.py, build_profiles.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from build_profiles import build, cristin_unit, staff_status  # noqa: E402
from collect_cristin import uis_affiliations  # noqa: E402
from directory import Directory  # noqa: E402

MATH = "Mathematics and Physics"
CHEM = "Chemistry, Bioscience and Environmental Engineering"


def aff(unit, active, nb="Professor", en="Professor"):
    return {"unit": unit, "active": active, "nb": nb, "en": en}


def test_uis_affiliations_keep_only_uis_units():
    record = {"affiliations": [
        {"organization": "https://api.nva.unit.no/cristin/organization/184.12.31.0", "active": True,
         "role": {"labels": {"en": "Head of department", "nb": "Instituttleder"}}},
        {"organization": "https://api.nva.unit.no/cristin/organization/217.8.10.0", "active": False,
         "role": {"labels": {"en": "Professor", "nb": "Professor"}}}]}
    assert uis_affiliations(record) == [aff("217.8.10.0", False)]
    assert uis_affiliations({}) == []


def test_staff_status():
    assert staff_status(True, None) == ("current", [])                     # employee directory
    assert staff_status(False, {"uis": [aff("217.8.10.0", True)]})[0] == "current"
    assert staff_status(False, {"uis": [aff("217.8.10.0", False)]}) == ("former", [])
    assert staff_status(False, {"uis": []}) == ("unknown", [])              # never at UiS in Cristin
    assert staff_status(False, None) == ("unknown", [])                     # no Cristin record


def test_cristin_unit_maps_to_atlas_department_or_faculty():
    assert cristin_unit([aff("217.8.10.0", True)])["departments"] == [CHEM]
    assert cristin_unit([aff("217.8.0.0", True)]) == {
        "departments": [], "faculty": "Faculty of Science and Technology", "excluded": False}
    assert cristin_unit([aff("217.0.0.0", True)]) is None


def test_build_uses_cristin_for_status_title_and_department():
    papers = {f"p{i}": {"title": "t", "year": "2025", "citations": 0, "keywords": [], "coauthor_ids": []}
              for i in range(9)}
    authors = [   # three NVA people with three recent UiS papers each, none in the directory
        {"scopus_id": f"nva-{n}", "cristin_id": n, "name": name, "department": MATH,
         "papers": [f"p{3 * k + j}" for j in range(3)]}
        for k, (n, name) in enumerate([(1, "Kari Nordmann"), (2, "Ola Hansen"), (3, "Liv Berg")])]
    cristin = {"1": {"uis": [aff("217.8.10.0", True)]},
               "2": {"uis": [aff("217.8.2.0", False)]}}
    res = build({"authors": authors, "papers": papers}, {}, {}, reference_year=2026,
                recent_years=3, min_recent=0, directory=Directory(None), unconfirmed_years=2,
                unconfirmed_min=3, cristin=cristin)
    kari, ola, liv = (res["people"][f"nva-{n}"] for n in (1, 2, 3))
    assert (kari["staff"], kari["position"]["en"], kari["department"]) == ("current", "Professor", CHEM)
    assert (ola["staff"], ola["position"], ola["department"]) == ("former", None, MATH)
    assert liv["staff"] == "unknown"
    assert all(p["included"] for p in (kari, ola, liv))     # inclusion rule unchanged


def test_cristin_inclusion_needs_an_academic_role():
    papers = {f"p{i}": {"title": "t", "year": "2025", "citations": 0, "keywords": [], "coauthor_ids": []}
              for i in (1, 2)}
    authors = [{"scopus_id": "nva-1", "cristin_id": 1, "name": "Kari Nordmann", "department": MATH,
                "papers": ["p1"]},
               {"scopus_id": "nva-2", "cristin_id": 2, "name": "Ola Hansen", "department": MATH,
                "papers": ["p2"]}]
    cristin = {"1": {"uis": [aff("217.8.2.0", True, nb="Førsteamanuensis", en="Associate professor")]},
               "2": {"uis": [aff("217.8.2.0", True, nb="Student", en="Student")]}}
    args = dict(reference_year=2026, recent_years=3, min_recent=0, directory=Directory(None),
                unconfirmed_years=2, unconfirmed_min=3, cristin=cristin)
    off = build({"authors": authors, "papers": papers}, {}, {}, **args)["people"]
    assert not off["nva-1"]["included"] and not off["nva-2"]["included"]     # opt-in
    on = build({"authors": authors, "papers": papers}, {}, {}, cristin_include_min=1, **args)["people"]
    assert on["nva-1"]["included"] and not on["nva-2"]["included"]          # students are not
    assert on["nva-2"]["staff"] == "current"
