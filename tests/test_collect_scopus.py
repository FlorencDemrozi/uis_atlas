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
