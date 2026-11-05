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


def test_successful_run_becomes_the_drop_baseline(tmp_path, monkeypatch):
    """The drop check compares with the last checked run, not with git HEAD (the server
    never commits data/public/)."""
    import json
    public = tmp_path / "meta.json"
    public.write_text(json.dumps({"n_researchers": 900, "n_papers": 40000}), encoding="utf-8")
    log = (tmp_path / "weekly-2026-11-07_0100.log").open("w", encoding="utf-8")
    monkeypatch.setattr(run_weekly, "LOGS", tmp_path)
    monkeypatch.setattr(run_weekly, "LOG", log)
    monkeypatch.setattr(run_weekly, "PUBLIC_META", public)
    monkeypatch.setattr(run_weekly, "CHECKED_META", tmp_path / "last-success-meta.json")
    run_weekly.record(True, "Finished (drop accepted with --allow-drop)")
    log.close()
    assert run_weekly.baseline_meta() == {"n_researchers": 900, "n_papers": 40000}
    assert run_weekly.sanity_check() == []
    public.write_text(json.dumps({"n_researchers": 500, "n_papers": 40000}), encoding="utf-8")
    assert run_weekly.sanity_check() == ["researchers 900 -> 500"]


def test_failed_run_does_not_move_the_baseline(tmp_path, monkeypatch):
    import json
    public = tmp_path / "meta.json"
    public.write_text(json.dumps({"n_researchers": 10, "n_papers": 10}), encoding="utf-8")
    log = (tmp_path / "weekly-2026-11-07_0100.log").open("w", encoding="utf-8")
    monkeypatch.setattr(run_weekly, "LOGS", tmp_path)
    monkeypatch.setattr(run_weekly, "LOG", log)
    monkeypatch.setattr(run_weekly, "PUBLIC_META", public)
    monkeypatch.setattr(run_weekly, "CHECKED_META", tmp_path / "last-success-meta.json")
    run_weekly.record(False, "sharp drop")
    log.close()
    assert not (tmp_path / "last-success-meta.json").exists()
