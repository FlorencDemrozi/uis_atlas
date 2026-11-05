"""NordForsk and Nordic Energy Research calls: status, deadlines, filtering, fields.

Fixtures in tests/fixtures/nordic/ are real records as stored by collect_nordic.py
(public data from www.nordforsk.org and www.nordicenergy.org, recorded 2026-11-05).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
import build_calls  # noqa: E402
import export_funding  # noqa: E402
import nordic  # noqa: E402
import profile_calls  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "nordic"
NF = json.loads((FIX / "nordforsk.json").read_text(encoding="utf-8"))
NER = json.loads((FIX / "nordicenergy.json").read_text(encoding="utf-8"))
TODAY = "2026-11-05"


def nf(nid: str, today: str = TODAY) -> dict:
    node = next(c for c in NF["calls"] if str(c["attributes"]["drupal_internal__nid"]) == nid)
    return nordic.build_nordforsk(node, NF["included"], NF["fetched"], today)


def ner(ident: int, today: str = TODAY) -> dict:
    item = next(i for i in NER["items"] if i["id"] == ident)
    return nordic.build_ner(item, NER["terms"], NER["fetched"], today)


def v(call: dict, key: str):
    return call["fields"][key]["v"]


def test_nordforsk_status_follows_the_call_dates():
    food = nf("1855")
    assert v(food, "status") == "open" and v(food, "deadline") == "2026-12-02"
    assert v(food, "opening_date") == "2026-06-23"
    assert v(nf("1855", today="2026-06-01"), "status") == "planned"
    assert v(nf("1855", today="2026-12-03"), "status") == "closed"


def test_nordforsk_fields_and_record_shape():
    c = nf("1856")
    assert c["id"] == "nordforsk-1856" and c["source"] == c["family"] == "nordforsk"
    assert v(c, "funder")["en"] == "NordForsk"
    assert v(c, "url")["en"].startswith("https://www.nordforsk.org/calls/")
    assert "Critical raw materials" in v(c, "themes")["en"]
    assert v(c, "summary")["en"].startswith("The aim is to fund about 24 Nordic projects")
    assert c["sections"]["en"] and not c["sections"]["nb"]
    # Every field of the shared model is present, so later stages can read any of them.
    assert set(nordic.ALL_FIELDS) <= set(c["fields"])
    assert all(set(f) == {"v", "s", "src", "url", "ev", "c", "m"} for f in c["fields"].values())


def test_safelinks_are_unwrapped_and_partner_sites_flagged():
    assert nordic.unwrap("https://eur03.safelinks.protection.outlook.com/?url=https%3A%2F%2Ffunding.nordforsk.org"
                         "%2F%23call%2F4685%2Fmain&data=x") == "https://funding.nordforsk.org/#call/4685/main"
    assert nordic.unwrap("https://example.org/a") == "https://example.org/a"
    docs = v(nf("1855"), "documents")
    assert docs[0]["url"] == "https://funding.nordforsk.org/#call/4685/main"
    assert not any("safelinks" in d["url"] for d in docs)
    assert any("partner's site" in r for r in nf("1853")["review"])  # SSHRC (Canada) runs the application


def test_ner_tenders_are_left_out():
    item = next(i for i in NER["items"] if i["id"] == 9227)
    assert nordic.is_tender(item, NER["terms"])
    assert not any(c["id"] == "nordicenergy-9227" for c in nordic.records(None, NER, TODAY))


def test_ner_deadline_from_text_with_inferred_year():
    c = ner(8229)  # "The deadline for submissions is 12 May at 13:00 (CEST)", published 2026-01-28
    assert v(c, "deadline") == "2026-05-12"
    assert c["fields"]["deadline"]["s"] == "inferred" and "publication date" in c["fields"]["deadline"]["ev"]
    assert v(c, "status") == "closed"
    full = ner(3468)  # the year is stated: explicit
    assert v(full, "deadline") == "2025-03-25" and full["fields"]["deadline"]["s"] == "explicit"


def test_ner_project_period_is_not_the_deadline():
    # "... must initiate no later than 3 September 2024 and end no later than 3 September 2028."
    assert v(ner(3455), "deadline") != "2028-09-03"


def test_ner_rolling_call_stays_open():
    c = ner(8230)  # "closes when the budget is exhausted or at the end of the year"
    assert v(c, "status") == "open" and v(c, "rolling") is True
    assert not c["review"]


def test_text_deadline_rules():
    assert nordic.text_deadline("Questions can be sent until 1 March. The deadline is 15 March.", "2026-01-10") \
        == ("2026-03-15", "The deadline is 15 March.", True)
    # A date before the publication date belongs to the next year.
    assert nordic.text_deadline("Deadline: 10 January", "2026-11-01")[0] == "2027-01-10"
    assert nordic.text_deadline("No dates here.", "2026-01-01") is None


def test_records_keep_open_calls_and_recent_closed_ones():
    ids = {c["id"] for c in nordic.records(NF, NER, TODAY)}
    assert {"nordforsk-1856", "nordforsk-1855", "nordforsk-1853", "nordicenergy-8230", "nordicenergy-8229"} <= ids
    assert "nordforsk-1467" not in ids        # closed November 2024: older than six months
    assert "nordicenergy-3468" not in ids


def test_sources_are_known_downstream():
    for src in ("nordforsk", "nordicenergy"):
        assert src in build_calls.SOURCES and src in export_funding.SOURCES and src in profile_calls.FUNDERS
    # Profiles read the English text of Nordic calls.
    assert "Title: Call for proposals: Nordic and Baltic" in profile_calls.call_text(nf("1855"))
