"""collect_rcn.py and collect_nordic.py when a source fails: previous data kept,
calls_listed not shrunk, non-zero exit code. No network: the fetchers are patched."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
import collect_nordic  # noqa: E402
import collect_rcn  # noqa: E402
import config  # noqa: E402

LISTS = [("https://rcn/list-nb", "current"), ("https://rcn/list-en", "current"),
         ("https://rcn/list-done", "completed")]


def list_props(*ids):
    return {"groups": [{"title": "G", "proposals": [{"id": i, "url": f"/call/{i}", "title": f"Call {i}"}
                                                    for i in ids]}]}


@pytest.fixture
def rcn_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_RUN_LOCKED", "1")
    monkeypatch.setattr(sys, "argv", ["collect_rcn.py"])
    monkeypatch.setattr(config, "RAW_RCN", tmp_path)
    monkeypatch.setattr(config, "RCN_LISTS", LISTS)
    monkeypatch.setattr(collect_rcn, "CALLS_DIR", tmp_path / "calls")
    monkeypatch.setattr(collect_rcn, "STATUS", tmp_path / "sync_status.json")
    monkeypatch.setattr(collect_rcn.rcn, "english_url", lambda page: None)
    monkeypatch.setattr(collect_rcn.rcn, "react_props",
                        lambda page, kind: page if kind == "ProposalListPage" else {"page": 1})
    return tmp_path


def run_rcn(monkeypatch, pages):
    """pages: url -> list props (or an exception to raise); call pages always work."""
    def get(self, url):
        page = pages.get(url, {})
        if isinstance(page, Exception):
            raise page
        return page
    monkeypatch.setattr(collect_rcn.Fetcher, "get", get)
    collect_rcn.main()


def test_rcn_partial_lists_keep_calls_listed_and_exit_1(rcn_env, monkeypatch):
    status_file = rcn_env / "sync_status.json"
    status_file.write_text(json.dumps({"calls_listed": ["1", "2", "3"], "last_success": "before"}), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        run_rcn(monkeypatch, {LISTS[0][0]: list_props("1", "4"), LISTS[1][0]: RuntimeError("timeout"),
                              LISTS[2][0]: list_props("3")})
    assert exc.value.code == 1
    status = json.loads(status_file.read_text(encoding="utf-8"))
    assert status["calls_listed"] == ["1", "2", "3", "4"]     # "2" is still listed; "4" added
    assert status["last_success"] == "before"
    assert status["errors"][0]["url"] == LISTS[1][0]
    assert (rcn_env / "calls" / "4.json").exists()             # what succeeded is saved
    assert not (rcn_env / "list_1.json").exists()


def test_rcn_all_lists_replace_calls_listed(rcn_env, monkeypatch):
    status_file = rcn_env / "sync_status.json"
    status_file.write_text(json.dumps({"calls_listed": ["1", "2", "3"]}), encoding="utf-8")
    run_rcn(monkeypatch, {LISTS[0][0]: list_props("1"), LISTS[1][0]: list_props("1"),
                          LISTS[2][0]: list_props("3")})   # no SystemExit: exit code 0
    status = json.loads(status_file.read_text(encoding="utf-8"))
    assert status["calls_listed"] == ["1", "3"] and status["last_success"] and not status["errors"]


def test_nordic_failed_source_keeps_old_file_and_exits_1(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_RUN_LOCKED", "1")
    monkeypatch.setattr(config, "RAW_NORDIC", tmp_path)
    monkeypatch.setattr(collect_nordic, "STATUS", tmp_path / "sync_status.json")
    (tmp_path / "nordicenergy.json").write_text('{"old": true}', encoding="utf-8")

    def broken(fetch):
        raise RuntimeError("site down")
    monkeypatch.setattr(collect_nordic, "SOURCES", {"nordforsk": lambda fetch: {"calls": [1, 2]},
                                                    "nordicenergy": broken})
    with pytest.raises(SystemExit) as exc:
        collect_nordic.main()
    assert exc.value.code == 1
    assert json.loads((tmp_path / "nordforsk.json").read_text(encoding="utf-8")) == {"calls": [1, 2]}
    assert json.loads((tmp_path / "nordicenergy.json").read_text(encoding="utf-8")) == {"old": True}
    status = json.loads((tmp_path / "sync_status.json").read_text(encoding="utf-8"))
    assert status["nordforsk"]["last_success"] and status["nordicenergy"]["errors"]
