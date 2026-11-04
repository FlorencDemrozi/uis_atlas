"""NVA trimming, unit mapping and the merge with Scopus, on small synthetic records."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
import config  # noqa: E402
from build_profiles import build  # noqa: E402
from nva import integrate, names_compatible, norm_doi, trim, unit_department  # noqa: E402

CS = "Electrical Engineering and Computer Science"
ORG = "https://api.nva.unit.no/cristin/organization/"


def hit(identifier, kind, title, year, contributors, doi=None):
    return {"identifier": identifier, "entityDescription": {
        "mainTitle": title, "publicationDate": {"year": str(year)}, "contributorsCount": len(contributors),
        "reference": {"doi": doi, "publicationInstance": {"type": kind},
                      "publicationContext": {"name": "Some Journal"}},
        "contributors": [{"role": {"type": role}, "identity": {"id": f"https://api.nva.unit.no/cristin/person/{pid}",
                                                               "name": name} if pid else {"name": name},
                          "affiliations": [{"id": ORG + unit}]} for pid, name, role, unit in contributors]}}


def test_trim_keeps_uis_contributors_with_an_id():
    rec = trim(hit("a1", "AcademicArticle", "T", 2024, [
        ("1", "Kari Nordmann", "Creator", "217.8.4.0"),
        ("2", "Elsewhere Person", "Creator", "194.0.0.0"),
        (None, "Unverified Name", "Creator", "217.8.4.0"),
    ], doi="https://doi.org/10.1/ABC"))
    assert rec["doi"] == "10.1/abc"
    assert [c["id"] for c in rec["contributors"]] == ["1"]
    assert rec["contributors"][0]["units"] == ["217.8.4.0"]


def test_unit_department():
    assert unit_department(["217.8.4.1"]) == CS                       # lab under the department
    assert unit_department(["217.8.11.0"]) == "Energy and Petroleum Engineering"
    assert unit_department(["217.8.1.0"]) == config.not_stated("Faculty of Science and Technology")
    assert unit_department(["217.9.2.0"]) is None                     # museum: not in the atlas
    assert unit_department(["217.6.5.10"]) == config.not_stated("Faculty of Arts and Education")


def test_names_and_doi():
    assert names_compatible("Klaus Mohn", "Klaus B. Mohn")
    assert names_compatible("Kari Berge", "Kari Berge Hansen")
    assert names_compatible("K. Mohn", "Klaus Mohn")
    assert not names_compatible("Klaus Mohn", "Kari Mohn")
    assert norm_doi("http://dx.doi.org/10.1/X") == "10.1/x"


def atlas():
    return {"authors": [{"scopus_id": "s1", "name": "Kari Nordmann", "orcid": None, "department": CS,
                         "papers": ["e1"], "uis_papers": ["e1"]}],
            "papers": {"e1": {"title": "A paper also registered in NVA", "year": "2025", "type": "Article",
                              "doi": "10.1/abc", "citations": 4, "keywords": [], "coauthor_ids": ["s1"]}}}


def records():
    return [
        trim(hit("n1", "AcademicArticle", "A paper also registered in NVA", 2025,
                 [("7", "Kari Nordmann", "Creator", "217.8.4.0")], doi="10.1/ABC")),
        trim(hit("n2", "AcademicChapter", "A chapter that Scopus does not index", 2025,
                 [("7", "Kari Nordmann", "Creator", "217.8.4.0")])),
        trim(hit("n3", "Lecture", "A lecture on the same topic", 2026,
                 [("7", "Kari Nordmann", "Creator", "217.8.4.0"), ("8", "Ola Supervisor", "Supervisor", "217.8.4.0")])),
        trim(hit("n4", "DegreeMaster", "A student thesis", 2025, [("9", "Student", "Creator", "217.8.4.0")])),
    ]


def test_integrate_dedupes_and_links_people():
    merged, links, stats = integrate(atlas(), records())
    assert links == [("nva-7", "s1")]
    assert stats["also in Scopus"] == 1 and stats["NVA only"] == 2
    assert merged["papers"]["e1"]["category"] == "article"
    assert merged["papers"]["nva-n2"]["category"] == "chapter"
    assert "nva-n4" not in merged["papers"]                            # student thesis
    ids = {a["scopus_id"] for a in merged["authors"]}
    assert "nva-8" not in ids                                          # supervisor role skipped
    nva7 = next(a for a in merged["authors"] if a["scopus_id"] == "nva-7")
    assert sorted(nva7["papers"]) == ["e1", "nva-n2", "nva-n3"] and nva7["department"] == CS


def test_profile_counts_publications_and_output_types():
    merged, links, _ = integrate(atlas(), records())
    res = build(merged, {}, {}, reference_year=2026, recent_years=2, min_recent=1, links=links)
    person = res["people"]["s1"]                                       # Scopus id stays the profile id
    assert person["scopus_ids"] == ["s1", "nva-7"]
    assert person["cristin_id"] == "7"
    assert person["n_publications"] == 2                               # article + chapter, not the lecture
    assert person["output_types"] == {"article": 1, "chapter": 1, "presentation": 1}
    assert person["citations"] == 4
    assert person["pubs_per_year"] == {"2025": 2}


def test_nva_duplicates_are_counted_once():
    recs = [
        trim(hit("d1", "AcademicChapter", "A chapter registered twice in NVA", 2024,
                 [("7", "Kari Nordmann", "Creator", "217.8.4.0")], doi="10.9/dup")),
        trim(hit("d2", "AcademicChapter", "A chapter registered twice in NVA", 2024,
                 [("8", "Ola Nordmann", "Creator", "217.8.4.0")], doi="10.9/DUP")),
        trim(hit("d3", "ReportResearch", "A report registered twice without any DOI", 2024,
                 [("7", "Kari Nordmann", "Creator", "217.8.4.0")])),
        trim(hit("d4", "ReportResearch", "A report registered twice without any DOI", 2024,
                 [("7", "Kari Nordmann", "Creator", "217.8.4.0")])),
        # Same DOI but a different kind of output (a talk about the paper): kept apart.
        trim(hit("d5", "ConferenceLecture", "A talk", 2024,
                 [("7", "Kari Nordmann", "Creator", "217.8.4.0")], doi="10.9/dup")),
    ]
    merged, _, stats = integrate({"authors": [], "papers": {}}, recs)
    assert stats["NVA only"] == 3 and stats["NVA duplicate"] == 2
    assert sorted(merged["papers"]["nva-d1"]["coauthor_ids"]) == ["nva-7", "nva-8"]
    assert "nva-d2" not in merged["papers"] and "nva-d4" not in merged["papers"]
    nva7 = next(a for a in merged["authors"] if a["scopus_id"] == "nva-7")
    assert nva7["papers"] == ["nva-d1", "nva-d3", "nva-d5"]


def test_unlinked_twin_still_listed_on_the_paper():
    """Kari's NVA record matches two different Scopus authors equally often, so she is
    not linked to either; the papers must still list her, as her profile lists them."""
    base = {"authors": [{"scopus_id": "s1", "name": "Kari Nordmann", "orcid": None, "department": CS,
                         "papers": ["e1"], "uis_papers": ["e1"]},
                        {"scopus_id": "s2", "name": "K. Nordmann", "orcid": None, "department": CS,
                         "papers": ["e2"], "uis_papers": ["e2"]}],
            "papers": {"e1": {"title": "First paper in both Scopus and NVA", "year": "2025", "type": "Article",
                              "doi": "10.1/a", "citations": 0, "keywords": [], "coauthor_ids": ["s1"]},
                       "e2": {"title": "Second paper in both Scopus and NVA", "year": "2025", "type": "Article",
                              "doi": "10.1/b", "citations": 0, "keywords": [], "coauthor_ids": ["s2"]}}}
    recs = [trim(hit("m1", "AcademicArticle", "First paper in both Scopus and NVA", 2025,
                     [("7", "Kari Nordmann", "Creator", "217.8.4.0")], doi="10.1/a")),
            trim(hit("m2", "AcademicArticle", "Second paper in both Scopus and NVA", 2025,
                     [("7", "Kari Nordmann", "Creator", "217.8.4.0")], doi="10.1/b"))]
    merged, links, _ = integrate(base, recs)
    assert links == []
    assert merged["papers"]["e1"]["coauthor_ids"] == ["s1", "nva-7"]
    assert merged["papers"]["e2"]["coauthor_ids"] == ["s2", "nva-7"]


def test_linked_twin_is_not_added_twice():
    merged, links, _ = integrate(atlas(), records())
    assert links == [("nva-7", "s1")]
    assert merged["papers"]["e1"]["coauthor_ids"] == ["s1"]
