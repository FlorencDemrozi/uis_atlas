"""collect_nva.py: an incomplete year keeps the stored file and fails the run. No network."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
import collect_nva  # noqa: E402
import config  # noqa: E402


def test_incomplete_rule():
    assert collect_nva.incomplete(98, 100, 0) is None
    assert collect_nva.incomplete(97, 100, 0)
    assert collect_nva.incomplete(0, 0, 0) is None
    assert collect_nva.incomplete(0, 0, 12)               # empty answer for a year that had records


def test_short_year_keeps_old_file_and_exits_1(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_RUN_LOCKED", "1")
    monkeypatch.setattr(sys, "argv", ["collect_nva.py"])
    monkeypatch.setattr(config, "RAW_NVA", tmp_path)
    monkeypatch.setattr(config, "RAW_NVA_STATE", tmp_path / "state.json")
    monkeypatch.setattr(config, "FIRST_YEAR", 2020)
    monkeypatch.setattr(config, "REFERENCE_YEAR", 2020)    # years 2020 and 2021, both refreshed
    monkeypatch.setattr(collect_nva, "Api", lambda: None)
    (tmp_path / "2020.jsonl").write_text('{"id": "old"}\n', encoding="utf-8")
    (tmp_path / "state.json").write_text(json.dumps({"years": {"2020": {"fetched": "x", "records": 1}}}),
                                         encoding="utf-8")
    results = {2020: ([{"id": i} for i in range(50)], 100), 2021: ([{"id": i} for i in range(10)], 10)}
    monkeypatch.setattr(collect_nva, "fetch_year", lambda api, year: results[year])
    with pytest.raises(SystemExit) as exc:
        collect_nva.main()
    assert exc.value.code == 1
    assert (tmp_path / "2020.jsonl").read_text(encoding="utf-8") == '{"id": "old"}\n'
    assert len((tmp_path / "2021.jsonl").read_text(encoding="utf-8").splitlines()) == 10
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["years"]["2020"] == {"fetched": "x", "records": 1} and state["years"]["2021"]["records"] == 10
