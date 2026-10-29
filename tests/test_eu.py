"""EU Funding & Tenders topics: parsing, hierarchy, rules and eligibility.

Fixtures in tests/fixtures/eu/ are real topic records as stored by collect_eu.py
(public data from the European Commission's portal, recorded 2026-10-29).
"""
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
import collect_eu  # noqa: E402
import config  # noqa: E402
import eu  # noqa: E402
import export_funding  # noqa: E402
import match_funding  # noqa: E402
import profile_calls  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "eu"
TODAY = "2026-10-29"
RAW = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in FIX.glob("*.json")}
NAMES = eu.programme_names(list(RAW.values()))


def build(ident: str, today: str = TODAY) -> dict:
    return eu.build_topic(RAW[ident], NAMES, today)


def v(call: dict, key: str):
    return call["fields"][key]["v"]


def test_dates_are_brussels_calendar_days():
    assert eu.to_date("1827619200000") == "2027-12-01"        # 00:00 UTC
    assert eu.to_date("1780264800000") == "2026-06-01"        # 22:00 UTC = midnight in Brussels (summer)
    assert eu.to_date("19 March 2024") == "2024-03-19"
    assert eu.to_date("2026-06-28T22:59:00.000+0000") == "2026-06-29"
    assert eu.to_date(None) is None and eu.to_date("soon") is None


def test_horizon_topic_hierarchy_budget_and_rules():
    c = build("HORIZON-CL5-2027-07-D3-32")
    assert c["id"] == "eu-HORIZON-CL5-2027-07-D3-32" and c["source"] == "eu" and c["family"] == "horizon"
    assert v(c, "programme")["en"] == "Horizon Europe (HORIZON)"
    assert v(c, "programme_part")["en"].endswith("Climate, Energy and Mobility > Energy Supply")
    assert "HORIZON-CL5-2027-07" in v(c, "parent_call")["en"]
    assert v(c, "action_type") == ["IA"]
    assert (v(c, "total_budget"), v(c, "max_amount"), v(c, "expected_grants"), v(c, "currency")) \
        == (30_000_000, 10_000_000, 3, "EUR")
    assert v(c, "deadline") == "2027-12-01" and v(c, "status") == "planned"
    # Programme-level rules are inferred, with their basis.
    for key in ("funding_rate", "consortium_size", "norway_eligible", "uis_can_apply"):
        assert c["fields"][key]["s"] == "inferred" and c["fields"][key]["m"] == "rule"
    assert v(c, "norway_eligible") is True
    # Official passages come from the topic text, under their heading.
    assert c["fields"]["research_scope"]["src"].endswith("Scope")
    assert c["fields"]["expected_impact"]["src"].endswith("Expected Outcome")
    assert v(c, "summary")["en"].startswith("Project results are expected to contribute")


def test_two_stage_topic_has_both_deadlines():
    c = build("HORIZON-JU-CHIPS-2026-1-IA", today="2026-01-01")
    assert c["family"] == "partnerships"
    assert v(c, "preliminary_deadline") < v(c, "full_proposal_deadline") == v(c, "deadline")
    assert c["fields"]["deadline"]["s"] == "inferred"


def test_status_listed_open_but_deadlines_passed_is_closed_by_rule():
    c = build("HORIZON-CL5-2027-07-D3-32", today="2028-06-01")
    assert v(c, "status") == "closed" and c["fields"]["status"]["s"] == "inferred"
    assert any("all deadlines have passed" in r for r in c["review"])


def test_bottom_up_calls_are_open_to_all_fields():
    for ident, fam in (("HORIZON-MSCA-2027-PF-01-01", "msca"), ("ERC-2027-COG", "erc")):
        c = build(ident)
        assert c["family"] == fam and v(c, "open_field") is True and c["fields"]["open_field"]["ev"]
    assert v(build("HORIZON-CL5-2027-07-D3-32"), "open_field") is None


def test_company_only_and_restricted_topics():
    acc = build("HORIZON-EIC-2026-ACCELERATOR-01")
    assert v(acc, "uis_can_apply") is False and v(acc, "open_field") is None
    restricted = build("DIGITAL-ECCC-2027-DEPLOY-CYBER-11-NCC")
    f = restricted["fields"]["norway_eligible"]
    assert f["v"] is None and f["s"] == "inferred" and "12(5" in f["ev"]
    person = {"position": {"nb": "Professor"}, "first_year": 2005}
    assert match_funding.eligibility(acc, person)["reason"] == "eu_company_only"
    assert match_funding.eligibility(restricted, person)["reason"] == "eu_restricted"
    assert match_funding.eligibility(build("HORIZON-CL5-2027-07-D3-32"), person)["status"] == "no_restriction_found"


def test_programme_without_known_norway_participation_is_check():
    c = build("HORIZON-CL5-2027-07-D3-32")
    c["fields"]["norway_eligible"] = {"v": None, "s": "not_specified"}
    c["fields"]["uis_can_apply"] = {"v": None, "s": "not_specified"}
    assert match_funding.eligibility(c, {"position": {"nb": "Professor"}})["reason"] == "eu_country_unknown"


def test_collector_listing_and_refetch_rules():
    entry = collect_eu.listing_entry({"url": "u", "metadata": {
        "identifier": ["X-1"], "type": ["1"], "status": ["31094502"], "esST_checksum": ["a"],
        "deadlineDate": ["2026-01-10T00:00:00.000+0000", "2026-09-10T00:00:00.000+0000"]}})
    assert entry["status"] == "open" and entry["deadline"].startswith("2026-09-10")   # last cut-off
    old = {"listing": dict(entry), "fetched": "2026-10-28T10:00:00", "details": {"x": 1}}
    assert not collect_eu.needs_fetch(entry, old, full=False)
    assert collect_eu.needs_fetch(dict(entry, checksum="b"), old, full=False)
    assert collect_eu.needs_fetch(dict(entry, status="closed"), old, full=False)
    closed = dict(entry, status="closed")
    assert not collect_eu.needs_fetch(closed, dict(old, listing=closed, fetched="2020-01-01T00:00:00"), full=False)


def test_export_slims_closed_eu_topics_and_drops_repeated_urls():
    c = build("HORIZON-CL5-2027-07-D3-32", today="2028-06-01")    # closed by then
    out = export_funding.slim({k: c.get(k) for k in export_funding.CALL_KEYS})
    assert set(out["fields"]) <= export_funding.CLOSED_EU_FIELDS
    assert "url" not in out["fields"]["title"]                      # same as the topic page
    assert all(val is not None for f in out["fields"].values() for val in f.values())
    current = export_funding.slim({k: v for k, v in build("HORIZON-CL5-2027-07-D3-32").items()
                                   if k in export_funding.CALL_KEYS})
    assert "research_scope" in current["fields"] and current["family"] == "horizon"


def test_erc_and_msca_role_rules():
    cog, pf = build("ERC-2027-COG"), build("HORIZON-MSCA-2027-PF-01-01")
    assert cog["fields"]["pi_requirements"]["s"] == "inferred" and "7 and up to 12" in v(cog, "pi_requirements")["en"]
    ref = config.REFERENCE_YEAR
    who = lambda position, years: {"position": {"nb": position}, "first_year": ref - years}
    phd = match_funding.eligibility(cog, who("Stipendiat", 4))
    assert (phd["status"], phd["reason"]) == ("likely_ineligible", "erc_doctorate") and "Consolidator" in phd["evidence"]
    assert match_funding.eligibility(cog, who("Førsteamanuensis", 11))["status"] == "no_restriction_found"
    # Career age is only an estimate (first publication, not PhD date): never more than "check".
    e = match_funding.eligibility(cog, who("Førsteamanuensis", 25))
    assert (e["status"], e["reason"]) == ("check", "erc_cog_window")
    # A short UiS record says little (earlier papers may be from elsewhere): no flag.
    assert match_funding.eligibility(cog, who("Førsteamanuensis", 4))["status"] == "no_restriction_found"
    assert match_funding.eligibility(pf, who("Stipendiat", 3))["reason"] == "msca_supervisor"
    assert match_funding.eligibility(pf, who("Postdoktor", 6))["status"] == "check"
    assert match_funding.eligibility(pf, who("Professor", 20))["status"] == "no_restriction_found"
    assert eu.role_rule("HORIZON-MSCA-2027-PF-01-01")[2] == "supervisor"
    assert eu.role_rule("HORIZON-MSCA-2027-SE-01-01")[2] == "secondment"
    assert eu.role_rule("HORIZON-CL5-2027-07-D3-32") is None


def test_cofund_is_institution_level():
    raw = copy.deepcopy(RAW["HORIZON-MSCA-2027-PF-01-01"])
    raw["id"] = raw["details"]["identifier"] = "HORIZON-MSCA-2027-COFUND-01-01"
    c = eu.build_topic(raw, NAMES, TODAY)
    assert v(c, "institution_level") is True and "COFUND" in c["fields"]["institution_level"]["ev"]
    assert v(build("HORIZON-MSCA-2027-PF-01-01"), "institution_level") is None


def test_eu_profile_prefilter():
    topic = build("HORIZON-CL5-2027-07-D3-32")
    cid = topic["id"]
    low, high = config.EU_PROFILE_MIN_SCORE - 0.1, config.EU_PROFILE_MIN_SCORE
    assert profile_calls.eu_wanted(topic, {cid: high}, {})
    assert not profile_calls.eu_wanted(topic, {cid: low}, {})
    assert profile_calls.eu_wanted(topic, {cid: low}, {cid: {}})  # keeps its profile while open
    assert not profile_calls.eu_wanted(build("ERC-2027-COG"), {"eu-ERC-2027-COG": 1.0}, {})  # open to all fields
    assert not profile_calls.eu_wanted(build("HORIZON-EIC-2026-ACCELERATOR-01"),
                                       {"eu-HORIZON-EIC-2026-ACCELERATOR-01": 1.0}, {})  # company only


def test_eu_scope_stays_official_text_with_a_profile():
    topic = build("HORIZON-CL5-2027-07-D3-32")
    profile = {"profile": {"disciplines": [{"path": ["Machine learning"], "level": "primary"}],
                           "topics": [{"path": ["Machine learning", "Diffusion models"], "basis": "explicit",
                                       "evidence": ""}],
                           "technologies": [], "contributing_expertise": [], "competencies": [],
                           "methods": [], "application_domains": []}}
    scope, aspects = match_funding.call_aspects(topic, profile)
    assert scope == match_funding.call_aspects(topic, None)[0] and "Machine learning" not in scope
    assert [a["label"] for a in aspects] == ["Diffusion models"]
