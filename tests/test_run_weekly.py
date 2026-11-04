"""Sanity check before the weekly run rebuilds and publishes the website."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
from run_weekly import count_drops  # noqa: E402


def test_small_changes_pass():
    assert count_drops({"n_researchers": 1141, "n_papers": 56529}, {"n_researchers": 1120, "n_papers": 56418}) == []


def test_sharp_drop_is_reported():
    assert count_drops({"n_researchers": 1141, "n_papers": 56529}, {"n_researchers": 1141, "n_papers": 20000}) \
        == ["papers 56529 -> 20000"]


def test_first_export_has_nothing_to_compare():
    assert count_drops({}, {"n_researchers": 10, "n_papers": 5}) == []
