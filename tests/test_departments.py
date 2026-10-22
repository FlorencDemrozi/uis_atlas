"""Department matching with renames, splits and most-recent-affiliation logic."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
from config import NOT_STATED  # noqa: E402
from departments import current_department, match_dept  # noqa: E402

CS = "Computer Science and Electrical Engineering"
CHEM = "Chemistry, Bioscience and Environmental Engineering"
EPE = "Energy and Petroleum Engineering"
ER = "Energy Resources"
SEP = "Safety, Economics and Planning"


def test_renamed_departments_map_to_todays_name():
    assert match_dept(["Department of Electrical and Computer Engineering"], 2005) == CS
    assert match_dept(["Dept. of Elec./Computer Engineering"], 2001) == CS
    assert match_dept(["Department of Industrial Economics, Risk Management and Planning"], 2012) == SEP
    assert match_dept(["Centre for Organelle Research (CORE)"], 2014) == CHEM


def test_split_departments_only_identify_the_faculty():
    assert match_dept(["Department of Mathematics and Natural Sciences"], 2010) == NOT_STATED
    assert match_dept(["Department of Petroleum Engineering"], 2012) == NOT_STATED
    # after the split the same words mean today's department
    assert match_dept(["Department of Petroleum Engineering"], 2020) == EPE
    assert match_dept(["Department of Energy Resources"], 2020) == ER


def test_other_faculties_are_not_matched():
    assert match_dept(["Department of Quality and Health Technology"], 2020) is None
    assert match_dept(["University of Stavanger"], 2020) is None


def test_most_recent_affiliation_wins():
    # long history in a split department, then a clear current department
    obs = [(2010, NOT_STATED)] * 5 + [(2015, EPE), (2016, EPE), (2023, ER), (2024, ER)]
    assert current_department(obs) == ER


def test_only_faculty_level_information():
    assert current_department([(2010, NOT_STATED), (2012, None)]) == NOT_STATED
    assert current_department([(2010, None)]) is None
