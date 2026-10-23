"""Department matching with renames, splits and most-recent-affiliation logic."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
import config  # noqa: E402
from config import not_stated  # noqa: E402
from departments import current_department, match_dept  # noqa: E402

EECS = "Electrical Engineering and Computer Science"
CHEM = "Chemistry, Bioscience and Environmental Engineering"
EPE = "Energy and Petroleum Engineering"
SEP = "Safety, Economics and Planning"
TN = not_stated("Faculty of Science and Technology")
HV = not_stated("Faculty of Health Sciences")


def test_renamed_departments_map_to_todays_name():
    assert match_dept(["Department of Electrical and Computer Engineering"], 2005) == EECS
    assert match_dept(["Dept. of Elec./Computer Engineering"], 2001) == EECS
    assert match_dept(["Department of Computer Science and Electrical Engineering"], 2024) == EECS
    assert match_dept(["Department of Industrial Economics, Risk Management and Planning"], 2012) == SEP
    assert match_dept(["Centre for Organelle Research (CORE)"], 2014) == CHEM


def test_merged_department_maps_to_its_successor():
    assert match_dept(["Department of Energy Resources"], 2020) == EPE
    assert match_dept(["Department of Petroleum Engineering"], 2012) == EPE


def test_split_departments_only_identify_the_faculty():
    assert match_dept(["Department of Mathematics and Natural Sciences"], 2010) == TN
    assert match_dept(["Department of Health Studies"], 2015) == HV


def test_other_faculties():
    assert match_dept(["Department of Quality and Health Technology"], 2020) == \
        "Department of Quality and Health Technology"
    assert match_dept(["Department of Early Childhood Education"], 2022) == \
        "Department of Early Childhood Education"
    assert match_dept(["Department of Economics and Finance", "UiS Business School"], 2022) == \
        "Department of Economics and Finance"
    assert match_dept(["Norwegian School of Hotel Management"], 2021) == \
        "NHS – Department of Leadership and Service Innovation"
    assert match_dept(["Department of Psychology"], 2025) == "Department of Psychology"
    assert match_dept(["Faculty of Health Sciences"], 2025) == HV
    assert match_dept(["UiS Business School"], 2025) == not_stated("UiS School of Business and Law")


def test_excluded_units_and_bare_university_are_not_matched():
    assert match_dept(["Norwegian Reading Centre", "Faculty of Arts and Education"], 2020) is None
    assert match_dept(["Museum of Archaeology"], 2020) is None
    assert match_dept(["University of Stavanger"], 2020) is None


def test_every_department_belongs_to_one_faculty():
    names = [d for d, _ in config.DEPARTMENTS]
    assert len(names) == len(set(names))
    assert all(config.FACULTY_OF[d] for d in names)
    assert len(config.FACULTIES) == 6


def test_most_recent_affiliation_wins():
    # long history in a split department, then a clear current department
    obs = [(2010, TN)] * 5 + [(2015, CHEM), (2016, CHEM), (2023, EPE), (2024, EPE)]
    assert current_department(obs) == EPE


def test_only_faculty_level_information():
    assert current_department([(2010, TN), (2012, None)]) == TN
    assert current_department([(2010, TN), (2022, HV)]) == HV
    assert current_department([(2010, None)]) is None
