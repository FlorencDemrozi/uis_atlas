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


# ------------------------------------------------ publications at other affiliations
def doc(eid, year, authors, affiliations):
    """A Scopus Search record: authors [(id, afid)], affiliations [(afid, name)]."""
    return {"eid": eid, "dc:title": f"Paper {eid}", "prism:coverDate": f"{year}-05-01", "citedby-count": "3",
            "affiliation": [{"afid": a, "affilname": n} for a, n in affiliations],
            "author": [{"authid": i, "authname": f"Author {i}", "surname": i, "given-name": "A",
                        "afid": [{"$": f}]} for i, f in authors]}


def test_build_credits_other_affiliations_by_author_id(tmp_path, monkeypatch):
    monkeypatch.setattr(collect_scopus, "FINAL_FILE", tmp_path / "atlas.json")
    monkeypatch.setattr(collect_scopus, "FIRST_YEAR", 2000)   # not the .env value: CI has no .env
    uis, verona = config.AFID, "999"
    docs = [
        doc("u1", 2024, [("A", uis), ("B", uis)], [(uis, "University of Stavanger")]),
        # B was at Verona on this one; the UiS co-author A put it in the UiS search
        doc("u2", 2021, [("A", uis), ("B", verona)], [(uis, "University of Stavanger"), (verona, "Verona")]),
    ]
    other = [doc("o1", 2019, [("B", verona), ("X", verona)], [(verona, "Verona")]),
             doc("o0", 1995, [("B", verona)], [(verona, "Verona")])]   # before ATLAS_FIRST_YEAR
    metrics = {"B": {"documents": 54, "citations": 827, "cited_by": 734, "h_index": 12, "fetched": "x"}}
    collect_scopus.build(docs, {}, other, metrics)
    out = json.loads((tmp_path / "atlas.json").read_text(encoding="utf-8"))
    a = {r["scopus_id"]: r for r in out["authors"]}
    assert set(a) == {"A", "B"}                       # X, an outside co-author, is not added
    assert sorted(a["B"]["papers"]) == ["o1", "u1", "u2"] and a["B"]["uis_papers"] == ["u1"]
    assert sorted(a["A"]["uis_papers"]) == ["u1", "u2"]
    assert a["B"]["scopus_metrics"]["h_index"] == 12 and "scopus_metrics" not in a["A"]
    assert "o0" not in out["papers"] and "o1" in out["papers"]


def test_author_query_excludes_uis_papers_and_parses_metrics():
    import collect_scopus_authors as ca
    q = ca.query(["1", "2"], 2000)
    assert q == f"(AU-ID(1) OR AU-ID(2)) AND NOT AF-ID({config.AFID}) AND PUBYEAR > 1999"
    many = {"author-retrieval-response-list": {"author-retrieval-response": [
        {"coredata": {"dc:identifier": "AUTHOR_ID:1", "document-count": "54", "citation-count": "827"},
         "h-index": "12"}]}}
    one = {"author-retrieval-response": [{"coredata": {"dc:identifier": "AUTHOR_ID:2", "document-count": "5"},
                                          "h-index": "2"}]}
    assert ca.parse_metrics(many)["1"] == {"documents": 54, "citations": 827, "cited_by": None, "h_index": 12}
    assert ca.parse_metrics(one)["2"]["h_index"] == 2
    assert [len(b) for b in ca.batches([str(i) for i in range(60)])] == [25, 25, 10]


def test_author_ids_drop_nva_pseudo_ids(tmp_path, monkeypatch):
    import collect_scopus_authors as ca
    profiles = tmp_path / "profiles.json"
    profiles.write_text(json.dumps({"researchers": [{"scopus_ids": ["123", "nva-4567"]},
                                                    {"scopus_ids": ["89", "123"]},
                                                    {"scopus_ids": ["nva-1"]}]}), encoding="utf-8")
    monkeypatch.setattr(config, "PROFILES", profiles)
    assert ca.author_ids() == ["123", "89"]


# ------------------------------------------------ interrupted writes, 404s, expired cursors
def test_readers_skip_a_broken_last_line_and_appends_start_a_new_line(tmp_path, monkeypatch):
    docs = tmp_path / "docs.jsonl"
    docs.write_text(json.dumps({"eid": "a"}) + "\n" + '{"eid": "b", "dc:ti', encoding="utf-8")   # killed mid-line
    assert [e["eid"] for e in collect_scopus.load_docs(docs)] == ["a"]
    collect_scopus.fsutil.append_jsonl(docs, [{"eid": "c"}])
    assert sorted(e["eid"] for e in collect_scopus.load_docs(docs)) == ["a", "c"]

    refresh = tmp_path / "refresh.jsonl"
    refresh.write_text(json.dumps({"eid": "d"}) + "\n{broken", encoding="utf-8")
    assert collect_scopus.merge_refresh(docs, refresh) == (1, 3)
    assert sorted(e["eid"] for e in read_jsonl(docs)) == ["a", "c", "d"]   # broken lines are gone

    details = tmp_path / "details.jsonl"
    details.write_text(json.dumps({"eid": "a", "authors": {"1": ["x"]}}) + "\n{\"eid\":", encoding="utf-8")
    monkeypatch.setattr(collect_scopus, "DETAILS_FILE", details)
    assert collect_scopus.load_details() == {"a": {"1": ["x"]}}


class FakeResponse:
    def __init__(self, status, body=None, headers=None):
        self.status_code, self._body, self.headers, self.text = status, body, headers or {}, ""

    def json(self):
        return self._body

    def raise_for_status(self):
        import requests
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)

    def get(self, url, params=None, timeout=None):
        return self.responses.pop(0)


def test_missing_paper_is_recorded_empty_and_not_fatal(tmp_path, monkeypatch):
    details = tmp_path / "details.jsonl"
    monkeypatch.setattr(collect_scopus, "DETAILS_FILE", details)
    monkeypatch.setattr(collect_scopus, "SLEEP", 0)
    assert collect_scopus.lookup_details(FakeSession([FakeResponse(404)]), "2-s2.0-1") == {}
    assert collect_scopus.load_details() == {"2-s2.0-1": {}}      # done: not asked again
    with pytest.raises(Exception):                                # other lookups still raise on 404
        collect_scopus.get(FakeSession([FakeResponse(404)]), "u", {})


def test_rejected_saved_cursor_restarts_search_once(tmp_path, monkeypatch):
    import requests
    out = tmp_path / "docs.jsonl"
    seen = []

    def fake_get(s, url, params, missing_ok=False):
        seen.append(params["cursor"])
        if params["cursor"] != "*":
            raise requests.HTTPError("400", response=FakeResponse(400))
        return {"search-results": {"entry": [{"eid": "a"}], "cursor": {"@next": "*"}}}

    monkeypatch.setattr(collect_scopus, "get", fake_get)
    state = {"cursor": "old", "done": False, "count": 50}
    collect_scopus.search(None, "q", state, out, lambda: None)
    assert seen == ["old", "*"] and state["done"] and state["count"] == 1
    assert [e["eid"] for e in read_jsonl(out)] == ["a"]

    def always_400(s, url, params, missing_ok=False):
        raise requests.HTTPError("400", response=FakeResponse(400))

    monkeypatch.setattr(collect_scopus, "get", always_400)
    with pytest.raises(requests.HTTPError):                       # only one restart
        collect_scopus.search(None, "q", {"cursor": "old", "done": False, "count": 0}, out, lambda: None)


def test_retry_after_is_honoured_and_capped():
    assert collect_scopus.retry_after(FakeResponse(429, headers={"Retry-After": "7"}), 2) == 7
    assert collect_scopus.retry_after(FakeResponse(429, headers={"Retry-After": "99999"}), 2) == config.MAX_RETRY_AFTER
    assert collect_scopus.retry_after(FakeResponse(429, headers={"Retry-After": "Wed, 21 Oct"}), 2) == 2
