"""What's new (build_changes.py): first-seen dates, identity keys, baseline and window."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
import build_changes as bc  # noqa: E402


def person(pid, email=None, nva=None):
    r = {"scopus_id": pid, "email": email, "links": {}}
    if nva:
        r["links"]["nva"] = f"https://nva.sikt.no/research-profile/{nva}"
    return r


def test_first_run_is_baseline_and_calls_are_seeded_from_history():
    state = {}
    history = {"c1": [{"date": "2026-10-27T11:00:00", "field": "new"}],
               "c2": [{"date": "2026-10-27T11:00:00", "field": "new"}, {"date": "2026-11-03T01:00:00", "field": "new"}],
               "c3": [{"date": "2026-11-03T01:00:00", "field": "new"}],
               "e1": [{"date": "2026-10-29T01:00:00", "field": "new"}]}   # a funder added later
    calls = [("c1", "rcn"), ("c2", "rcn"), ("c3", "rcn"), ("e1", "eu")]
    first = bc.update(state, [person("1", "a@uis.no")], calls, "2026-11-10", history)
    assert state["baseline"] == {"researchers": "2026-11-10", "calls": {"rcn": "2026-10-27", "eu": "2026-10-29"}}
    assert bc.recent(first, state["baseline"]["researchers"], "2026-11-10") == []
    # c2 counts from its first appearance; only c3 is new after the first funding run.
    assert bc.new_calls(state, {"c1", "c2", "c3", "e1"}, "2026-11-10") == [{"date": "2026-11-03", "ids": ["c3"]}]
    # A call of a new source: baseline for that source, not new; the next one is.
    bc.update(state, [], calls + [("n1", "nordforsk")], "2026-11-17")
    bc.update(state, [], calls + [("n1", "nordforsk"), ("n2", "nordforsk")], "2026-11-24")
    assert bc.new_calls(state, {"n1", "n2"}, "2026-11-24") == [{"date": "2026-11-24", "ids": ["n2"]}]
    assert bc.new_calls(state, {"c1", "c2"}, "2026-11-10") == []   # closed calls are left out


def test_new_researcher_but_not_a_changed_id():
    state = {}
    bc.update(state, [person("nva-42", "b@uis.no", nva="42"), person("7", "c@uis.no")], [], "2026-11-01")
    first = bc.update(state, [
        person("5555", "b@uis.no", nva="42"),      # NVA-only profile now has a Scopus id
        person("8", "C@uis.no"),                   # Scopus id changed, same e-mail
        person("9", "d@uis.no"),                   # really new
    ], [], "2026-11-08")
    assert bc.recent(first, state["baseline"]["researchers"], "2026-11-08") == [{"date": "2026-11-08", "ids": ["9"]}]
    # Missing for a week and back: still first seen on 2026-11-08, not new again.
    bc.update(state, [], [], "2026-11-15")
    first = bc.update(state, [person("9", "d@uis.no")], [], "2026-11-22")
    assert first["9"] == "2026-11-08"


def test_window_and_order():
    first = {"a": "2026-09-01", "b": "2026-11-01", "c": "2026-11-08", "d": "2026-11-08"}
    got = bc.recent(first, "2026-08-01", "2026-11-10", days=56)
    assert got == [{"date": "2026-11-08", "ids": ["c", "d"]}, {"date": "2026-11-01", "ids": ["b"]}]


def test_cristin_key_for_nva_profiles_without_link():
    assert "cristin:42" in bc.researcher_keys({"scopus_id": "nva-42", "links": {}})
