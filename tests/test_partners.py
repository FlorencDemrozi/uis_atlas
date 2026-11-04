"""External partner institutions (build_partners.py, export_public.export_partners) and
the directory e-mail parser (collect_directory.email_of)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import build_partners  # noqa: E402
import collect_directory  # noqa: E402
import config  # noqa: E402
from export_public import export_partners  # noqa: E402


def entry(eid, authors, affiliations, count=None):
    return {"eid": eid, "author-count": {"$": str(count or len(authors))},
            "author": [{"authid": a, "afid": [{"$": x} for x in afs]} for a, afs in authors],
            "affiliation": [{"afid": a, "affilname": n, "affiliation-city": c, "affiliation-country": k}
                            for a, n, c, k in affiliations]}


AFF = [(config.AFID, "University of Stavanger", "Stavanger", "Norway"),
       ("1", "NTNU", "Trondheim", "Norway"), ("2", "MIT", "Cambridge", "United States"),
       ("3", "Harvard", "Cambridge", "United States"), ("9", "Stavanger University Hospital", "Stavanger", "Norway")]


def test_partners_exclude_uis_and_the_researcher_own_affiliation():
    e = entry("e1", [("me", [config.AFID, "2"]), ("co", ["1"]), ("uis", [config.AFID])], AFF)
    # The researcher's own second affiliation (MIT) is not a partner; UiS never is.
    assert build_partners.partners_of_paper(e, {"me"}) == {"1"}


def test_hospital_is_a_partner_not_uis():
    e = entry("e1", [("me", [config.AFID]), ("co", ["9"])], AFF)
    assert build_partners.partners_of_paper(e, {"me"}) == {"9"}


def test_unknown_author_gives_none():
    e = entry("e1", [("x", ["1"])], AFF)
    assert build_partners.partners_of_paper(e, {"me"}) is None


def test_build_counts_papers_per_institution_and_country():
    entries = {
        "e1": entry("e1", [("me", [config.AFID]), ("a", ["2"]), ("b", ["3"])], AFF),   # 2 US institutions
        "e2": entry("e2", [("me", [config.AFID]), ("a", ["2"]), ("c", ["1"])], AFF),
        "e3": entry("e3", [("me", [config.AFID]), ("a", ["1"])], AFF, count=200),       # consortium: left out
    }
    profiles = [{"scopus_id": "me", "scopus_ids": ["me"], "paper_ids": ["e1", "e2", "e3", "nva-1"]}]
    out = build_partners.build(profiles, entries, max_authors=50)
    me = out["researchers"]["me"]
    assert me["institutions"] == {"2": 2, "3": 1, "1": 1}
    assert me["countries"] == {"United States": 2, "Norway": 1}   # e1 counts once for the US
    assert out["institutions"]["2"] == {"name": "MIT", "city": "Cambridge", "country": "United States"}
    assert out["skipped_large"] == 1


def test_export_keeps_only_researchers_on_the_site():
    partners = {"institutions": {"1": {"name": "NTNU", "city": "Trondheim", "country": "Norway"},
                                 "2": {"name": "MIT", "city": "Cambridge", "country": "United States"}},
                "researchers": {"me": {"institutions": {"1": 3}, "countries": {"Norway": 3}},
                                "gone": {"institutions": {"2": 1}, "countries": {"United States": 1}}}}
    out = export_partners(partners, {"me"})
    assert out == {"institutions": {"1": ["NTNU", "Trondheim", "Norway"]},
                   "researchers": {"me": {"i": [["1", 3]], "c": [["Norway", 3]]}}}


def test_email_from_profile_page():
    page = ('<a href="mailto:post@uis.no">post</a> '
            '<a href="mailto:Kari.Nordmann@uis.no?subject=x">Kari.Nordmann@uis.no</a>')
    assert collect_directory.email_of(page) == "kari.nordmann@uis.no"
    assert collect_directory.email_of("<p>no address</p>") is None
