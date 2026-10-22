"""Stage 2 logic on small synthetic data (no Scopus content in the repo)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
from build_profiles import build, given_compatible  # noqa: E402

CS = "Computer Science and Electrical Engineering"
MATH = "Mathematics and Physics"


def paper(year, coauthors, keywords=()):
    return {"title": "t", "year": str(year), "citations": 1, "keywords": list(keywords),
            "coauthor_ids": coauthors}


def author(auid, name, dept, papers, orcid=None):
    return {"scopus_id": auid, "name": name, "orcid": orcid, "department": dept, "papers": papers}


def run(authors, papers, overrides=None, min_recent=2):
    atlas = {"authors": authors, "papers": papers}
    return build(atlas, {}, overrides or {}, reference_year=2026, recent_years=2,
                 min_recent=min_recent)


def test_given_name_compatibility():
    assert given_compatible("Lennart", "L.")
    assert given_compatible("Emiel A.M.", "Emiel")
    assert not given_compatible("Yu", "Yucong")
    assert not given_compatible("Jasna", "Jan Tore")


def test_merges_by_orcid_and_by_name_with_shared_coauthor():
    papers = {f"p{i}": paper(2025, [a, "x"]) for i, a in enumerate("abcdd")}
    papers["p5"] = paper(2025, ["e", "x"])
    authors = [
        author("a", "Kari Nordmann", CS, ["p0"], orcid="0000-1"),
        author("b", "K. Nordmann", CS, ["p1"], orcid="0000-1"),
        author("c", "Ola Hansen", CS, ["p2"]),
        author("d", "O. Hansen", CS, ["p3", "p4"]),      # shares co-author x with c
        author("e", "Yucong Ma", CS, ["p5"]),
    ]
    papers["p6"] = paper(2025, ["f", "x"])
    authors.append(author("f", "Yu Ma", CS, ["p6"]))
    res = run(authors, papers)
    people = res["people"]
    assert {"a", "b"} == set(next(p for p in people.values() if "a" in p["scopus_ids"])["scopus_ids"])
    assert people["d"]["scopus_ids"] == ["d", "c"]       # main id = most papers
    assert "e" in people and "f" in people               # Yu Ma != Yucong Ma
    assert any(set(c["ids"]) == {"e", "f"} for c in res["candidates"])


def test_never_merges_two_authors_of_the_same_paper():
    papers = {"p": paper(2025, ["a", "b"])}
    res = run([author("a", "Ola Hansen", CS, ["p"]), author("b", "O. Hansen", CS, ["p"])], papers)
    assert len(res["people"]) == 2


def test_inclusion_counts_recent_and_in_press_papers():
    papers = {"old": paper(2021, ["a"]), "new": paper(2025, ["a"]), "press": paper(2027, ["a"]),
              "b1": paper(2025, ["b"])}
    res = run([author("a", "A A", CS, ["old", "new", "press"]), author("b", "B B", CS, ["b1"])],
              papers)
    a, b = res["people"]["a"], res["people"]["b"]
    assert (a["n_publications"], a["n_recent"], a["included"]) == (3, 2, True)
    assert a["paper_ids"] == ["press", "new", "old"]
    assert b["included"] is False


def test_overrides_and_collaboration_fields():
    papers = {"p1": paper(2025, ["a", "b"], ["LiDAR"]), "p2": paper(2026, ["a", "b"], ["lidar"])}
    authors = [author("a", "A A", CS, ["p1", "p2"]), author("b", "B B", CS, ["p1", "p2"])]
    res = run(authors, papers, overrides={"b": {"department": MATH, "include": False}})
    a, b = res["people"]["a"], res["people"]["b"]
    assert b["department"] == MATH and b["included"] is False
    assert a["keywords"] == [["LiDAR", 2]]
    assert a["top_coauthors"] == []                      # excluded people are not linked
    assert a["collab_departments"] == {MATH: 2}
