"""Sanity check before the weekly run rebuilds and publishes the website."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
import run_weekly  # noqa: E402
from run_weekly import count_drops  # noqa: E402


def test_small_changes_pass():
    assert count_drops({"n_researchers": 1141, "n_papers": 56529}, {"n_researchers": 1120, "n_papers": 56418}) == []


def test_sharp_drop_is_reported():
    assert count_drops({"n_researchers": 1141, "n_papers": 56529}, {"n_researchers": 1141, "n_papers": 20000}) \
        == ["papers 56529 -> 20000"]


def test_first_export_has_nothing_to_compare():
    assert count_drops({}, {"n_researchers": 10, "n_papers": 5}) == []


def test_record_writes_last_run_and_last_success(tmp_path, monkeypatch):
    import json
    log = (tmp_path / "weekly-2026-11-07_0100.log").open("w", encoding="utf-8")
    monkeypatch.setattr(run_weekly, "LOGS", tmp_path)
    monkeypatch.setattr(run_weekly, "LOG", log)
    run_weekly.record(True, "Finished in 31 min")
    run_weekly.record(False, "a processing stage failed")
    log.close()
    last = json.loads((tmp_path / "last-run.json").read_text(encoding="utf-8"))
    ok = json.loads((tmp_path / "last-success.json").read_text(encoding="utf-8"))
    assert (last["ok"], last["message"]) == (False, "a processing stage failed")
    assert (ok["ok"], ok["log"]) == (True, "weekly-2026-11-07_0100.log")
