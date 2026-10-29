"""Weekly refresh of the Scopus collector: merging, query scope, unattended runs."""
import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
import collect_scopus  # noqa: E402
import config  # noqa: E402


def write_jsonl(path, records):
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_merge_refresh_replaces_dedupes_and_adds(tmp_path):
    docs, refresh = tmp_path / "docs.jsonl", tmp_path / "refresh.jsonl"
    write_jsonl(docs, [{"eid": "a", "citedby-count": "1"}, {"eid": "b"}, {"eid": "a", "citedby-count": "2"}])
    write_jsonl(refresh, [{"eid": "a", "citedby-count": "5"}, {"eid": "c"}])
    new, total = collect_scopus.merge_refresh(docs, refresh)
    assert (new, total) == (1, 3)
    merged = {r["eid"]: r for r in read_jsonl(docs)}
    assert merged["a"]["citedby-count"] == "5"       # refreshed record wins
    assert set(merged) == {"a", "b", "c"}             # old papers are kept
    assert not refresh.exists()
    assert not docs.with_suffix(".tmp").exists()


def test_refresh_query_covers_recent_years_only():
    first = max(config.FIRST_YEAR, date.today().year - config.SCOPUS_REFRESH_YEARS + 1)
    assert collect_scopus.REFRESH_QUERY == f"AF-ID({config.AFID}) AND PUBYEAR > {first - 1}"


def test_unattended_run_without_key_stops(monkeypatch):
    monkeypatch.setattr(collect_scopus, "SCOPUS_API_KEY", None)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
    with pytest.raises(SystemExit):
        collect_scopus.make_session()
