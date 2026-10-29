"""Funding Intelligence: RCN parsing, structured extraction, eligibility, matching
rules, AI-output verification and the encrypted export. Offline: synthetic pages
shaped like forskningsradet.no's embedded JSON, no network or model needed."""
import base64
import gzip
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import build_calls  # noqa: E402
import config  # noqa: E402
import export_funding  # noqa: E402
import match_funding  # noqa: E402
import profile_calls  # noqa: E402
import rcn  # noqa: E402


# ------------------------------------------------------------------ fixtures
def html(*paras: str) -> dict:
    return {"blocks": [{"componentName": "HtmlString", "componentData": {"text": "".join(paras)}}]}


def tibi_page(title, meta_left, meta_right, sections, byline=("Publisert 21. jan. 2026", "Oppdatert 30. jul. 2026")):
    """A structured call page ("TibiProposalPage")."""
    return {
        "title": title,
        "preamble": html("<p>Kort om utlysningen.</p>"),
        "header": {"byline": {"items": [{"text": t} for t in byline]}},
        "metadataLeft": {"items": [{"label": k, "text": v} for k, v in meta_left.items()]},
        "metadataRight": {"items": [{"label": k, "text": v} for k, v in meta_right.items()]},
        "tabs": {"items": [{"name": "Utlysning", "content": {"tibi": {"contentSections": [
            {"sectionTitle": sec, "sectionText": html(), "subSections": [
                {"title": sub, "text": html(text)} for sub, text in subs]}
            for sec, subs in sections]}}}]},
        "timelineHorizontal": {"items": [{"title": "1. jan. 2027", "subTitle": "Tidligste tillatte prosjektstart"}]},
    }


def raw_call(cid, page, status="Søk nå", date="27. mai", timeframe="current", international=False, en=None):
    return {"id": cid, "url": f"https://www.forskningsradet.no/utlysninger/2026/{cid}/", "en_url": None,
            "fetched": "2026-10-26T10:00:00", "nb": page, "en": en,
            "listing": {"id": cid, "title": page["title"], "url": "", "group": "", "date": date, "year": "2026",
                        "status": status, "metadata": {}, "tags": [], "text": "",
                        "international": international, "timeframe": timeframe}}


FUNDAMENTAL = tibi_page(
    "Forskerprosjekt for tidlig karriere (FRIPRO)",
    {"Finansieringsordning": "Forskerprosjekt", "Søknadsfrist": "27. mai 2026, kl. 13.00 CEST",
     "Målgrupper": "Forskningsorganisasjon"},
    {"Støttegrenser": "Kr 4 000 000-10 000 000", "Antatt tilgjengelige midler": "Kr 510 000 000. FRIPROs budsjett …",
     "Prosjektvarighet": "36-48 måneder"},
    [("Om utlysningen", [("Formål", "<p>Nysgjerrighetsdreven forskning innen alle fag.</p>")]),
     ("Hvem kan delta i prosjektet?", [
         ("Krav til prosjektansvarlig organisasjon", "<p>Prosjektansvarlig må være en godkjent forskningsorganisasjon.</p>"),
         ("Krav til prosjektleder", "<p>Prosjektleder må ha avlagt doktorgrad for 2–7 år siden (tidlig karriere).</p>")]),
     ("Vurdering", [("Forskningsfaglig kvalitet", "<p>Originalitet og soliditet vurderes.</p>")]),
     ("Behandlingsprosedyre", [("Vurdering av om søknaden oppfyller strukturelle føringer satt i utlysningen",
                                "<p>Administrasjonen vurderer formelle krav.</p>")])])

COMMERCIAL = tibi_page(
    "Innovasjonsprosjekt i næringslivet: Sjømat 2026",
    {"Finansieringsordning": "Innovasjonsprosjekt i næringslivet", "Søknadsfrist": "Løpende",
     "Målgrupper": "Næringsliv, Forskningsorganisasjon"},
    {"Støttegrenser": "inntil kr 10 000 000", "Prosjektvarighet": "12-48 måneder"},
    [("Hvem kan delta i prosjektet?", [
        ("Krav til prosjektansvarlig", "<p>Prosjektansvarlig må være registrert i Foretaksregisteret og være en bedrift.</p>")])])


# --------------------------------------------------------------- parsing
def test_react_props_reads_embedded_json():
    page = 'x window.__REACT_COMPONENTS__.push({ id: "a", name: "TibiProposalPage", props: {"title": "T", "n": [1]} });'
    assert rcn.react_props(page, "ProposalPage") == {"title": "T", "n": [1]}
    assert rcn.react_props(page, "ProposalListPage") is None


@pytest.mark.parametrize("text,expected", [
    ("Kr 4 000 000-14 000 000", {"currency": "NOK", "min": 4_000_000, "max": 14_000_000}),
    ("inntil kr 500 000", {"currency": "NOK", "max": 500_000}),
    ("minimum kr 100 000", {"currency": "NOK", "min": 100_000}),
    ("Kr 118 000 000. 5 mill. kroner er øremerket …", {"currency": "NOK", "value": 118_000_000}),
    ("Kr 5 000 000. 0,5 mill. kroner pr. nettverk.", {"currency": "NOK", "value": 5_000_000}),
    ("€ 600 000", {"currency": "EUR", "value": 600_000}),
    ("", {}), (None, {}),
])
def test_parse_money(text, expected):
    assert rcn.parse_money(text) == expected


def test_parse_months_and_dates():
    assert rcn.parse_months("36-72 måneder") == {"min": 36, "max": 72}
    assert rcn.parse_months("maksimum 12 måneder") == {"max": 12}
    assert rcn.parse_months("4 years") == {"max": 48}
    assert rcn.parse_date("27. mai 2026, kl. 13.00 CEST") == "2026-05-27T13:00"
    assert rcn.parse_date("1. jan. 2027") == "2027-01-01"
    assert rcn.parse_date("May 27, 2026 at 13:00") == "2026-05-27T13:00"
    assert rcn.parse_date("Løpende") is None


def test_sections_both_layouts():
    secs = rcn.sections(FUNDAMENTAL)
    assert ["Hvem kan delta i prosjektet?", "Krav til prosjektleder"] in [s["path"] for s in secs]
    simple = {"descriptionTitle": "Om utlysningen", "descriptionText": html(
        "<p>Innledning.</p><h3>Hvem kan søke?</h3><p>Forskningsorganisasjoner.</p><ul><li>Punkt A</li></ul>")}
    secs = rcn.sections(simple)
    assert secs[0]["path"] == ["Om utlysningen"]
    assert secs[1]["path"] == ["Om utlysningen", "Hvem kan søke?"]
    assert "• Punkt A" in secs[1]["text"]


# ---------------------------------------------------- structured extraction
def test_fundamental_call_fields_have_values_and_sources():
    c = build_calls.build_call(raw_call("1", FUNDAMENTAL))
    f = c["fields"]
    assert f["deadline"]["v"] == "2026-05-27T13:00" and f["deadline"]["src"] == "Søknadsfrist"
    assert (f["min_amount"]["v"], f["max_amount"]["v"], f["total_budget"]["v"]) == (4_000_000, 10_000_000, 510_000_000)
    assert f["currency"]["v"] == "NOK"
    assert (f["min_duration_months"]["v"], f["max_duration_months"]["v"]) == (36, 48)
    assert f["earliest_start"]["v"] == "2027-01-01"
    assert f["published"]["v"] == "2026-01-21" and f["updated"]["v"] == "2026-07-30"
    assert f["orientation"] == {**f["orientation"], "v": "fundamental", "s": "inferred", "m": "rule"}
    assert f["uis_can_apply"]["v"] is True
    assert "doktorgrad" in f["pi_requirements"]["v"]["nb"]
    for key, fv in f.items():  # every stated value names where it came from
        if fv["s"] != "not_specified":
            assert fv["src"] and fv["m"], key


def test_missing_values_are_not_specified_not_guessed():
    f = build_calls.build_call(raw_call("1", FUNDAMENTAL))["fields"]
    for key in build_calls.AI_ONLY_FIELDS + ["preliminary_deadline", "programme"]:
        assert f[key]["s"] == "not_specified" and f[key]["v"] is None, key


def test_long_heading_does_not_count_as_structural_guidelines():
    f = build_calls.build_call(raw_call("1", FUNDAMENTAL))["fields"]
    assert f["structural_requirements"]["s"] == "not_specified"
    assert f["evaluation_criteria"]["s"] == "explicit"  # whole "Vurdering" section


def test_commercialisation_call_rolling_and_uis_only_partner():
    f = build_calls.build_call(raw_call("2", COMMERCIAL, date="Løpende"))["fields"]
    assert f["rolling"]["v"] is True and f["deadline"]["s"] == "not_specified"
    assert f["max_amount"]["v"] == 10_000_000 and f["min_amount"]["s"] == "not_specified"
    assert f["orientation"]["v"] == "innovation"
    assert f["uis_can_apply"]["v"] is False  # project owner must be a company


def test_open_field_call_is_recognised_from_its_text():
    page = tibi_page("Forskerprosjekt for erfarne forskere (FRIPRO)", {"Målgrupper": "Forskningsorganisasjon"}, {}, [
        ("Om utlysningen", [("Formål", "<p>Utlysningen er åpen for søknader innenfor alle fag- og forskningsområder.</p>")])])
    f = build_calls.build_call(raw_call("7", page))["fields"]
    assert f["open_field"]["v"] is True and "alle fag" in f["open_field"]["ev"]
    assert build_calls.build_call(raw_call("2", COMMERCIAL))["fields"]["open_field"]["s"] == "not_specified"


def test_international_call_flag():
    f = build_calls.build_call(raw_call("3", FUNDAMENTAL, international=True))["fields"]
    assert f["international"]["v"] is True and f["international"]["s"] == "explicit"


@pytest.mark.parametrize("status,timeframe,date,expected", [
    ("Søk nå", "current", "27. mai", "open"), ("Planlagt", "current", "Kommer", "planned"),
    ("Se Resultat", "current", "Løpende", "open"),  # rolling FRIPRO: results of earlier rounds published
    ("Se Resultat", "completed", "Løpende", "closed"), ("Gjennomført", "completed", "1. mars", "closed"),
])
def test_status_mapping(status, timeframe, date, expected):
    listing = {"status": status, "timeframe": timeframe, "date": date}
    assert build_calls.status_of(listing, {}) == expected


def test_open_call_with_past_deadline_is_flagged_for_review():
    page = dict(FUNDAMENTAL, metadataLeft={"items": [{"label": "Søknadsfrist", "text": "1. jan. 2020"}]})
    assert "listed as open but the deadline has passed" in build_calls.build_call(raw_call("4", page))["review"]


@pytest.mark.parametrize("label,kind", [
    ("Søknadsfrist", "deadline"), ("Skissefrist", "preliminary_deadline"),
    ("Full proposal - by invitation only", "full_proposal_deadline"), ("Åpner for søknad", "opening_date"),
    ("Søknadsfrist trinn 1", "preliminary_deadline"), ("Prosjektvarighet", None),
])
def test_deadline_labels(label, kind):
    assert build_calls.deadline_kind(label) == kind


def test_manual_correction_wins():
    c = build_calls.build_call(raw_call("1", FUNDAMENTAL))
    build_calls.apply_overrides(c, {"rcn-1": {"fields": {"deadline": {"v": "2026-06-01T13:00", "note": "RCN moved it"}}}})
    assert c["fields"]["deadline"]["v"] == "2026-06-01T13:00" and c["fields"]["deadline"]["m"] == "manual"


def test_call_ids_are_unique_in_built_data():
    if not config.CALLS.exists():
        pytest.skip("no calls built")
    ids = [c["id"] for c in json.loads(config.CALLS.read_text(encoding="utf-8"))["calls"]]
    assert len(ids) == len(set(ids))


# ------------------------------------------------------------- eligibility
def person(position, first_year=2015):
    return {"position": {"nb": position}, "first_year": first_year}


def test_ineligible_researcher_with_strong_alignment_is_not_presented_as_eligible():
    call = build_calls.build_call(raw_call("1", FUNDAMENTAL))
    e = match_funding.eligibility(call, person("Professor"))
    assert e["status"] == "likely_ineligible" and e["reason"] == "early_career_senior"
    assert "tidlig karriere" in e["evidence"].lower()
    # a "high" scientific match does not change that, nor make them PI candidate
    assert match_funding.suggested_role("high", e, "professor") == "team_member"


def test_sister_call_mentions_do_not_trigger_the_other_rule():
    """FRIPRO 'experienced' mentions 'tidlig karriere' in a rule about ongoing projects."""
    page = tibi_page("Forskerprosjekt for erfarne forskere (FRIPRO)", {"Målgrupper": "Forskningsorganisasjon"}, {}, [
        ("Hvem kan delta i prosjektet?", [("Prosjektleder",
          "<ul><li>Erfaring: Du må ha godkjent doktorgrad, og det må ha gått minst seks år.</li>"
          "<li>Pågående prosjekt: gjelder toppforskere, erfarne forskere, tidlig karriere eller internasjonal mobilitet.</li></ul>")])])
    call = build_calls.build_call(raw_call("8", page))
    assert match_funding.eligibility(call, person("Professor", 2005))["status"] == "no_restriction_found"
    junior = match_funding.eligibility(call, person("Postdoktor", 2021))
    assert junior["status"] == "likely_ineligible" and "minst seks år" in junior["evidence"]


def test_eligibility_partner_only_and_doctorate():
    commercial = build_calls.build_call(raw_call("2", COMMERCIAL))
    assert match_funding.eligibility(commercial, person("Førsteamanuensis"))["status"] == "partner_only"
    assert match_funding.suggested_role("high", match_funding.eligibility(commercial, person("Professor")),
                                        "professor") == "rd_partner"
    phd = match_funding.eligibility(build_calls.build_call(raw_call("1", FUNDAMENTAL)), person("Stipendiat", 2023))
    assert phd["status"] == "likely_ineligible"


def test_no_restriction_found_is_not_called_eligible():
    plain = tibi_page("Samarbeidsprosjekt", {"Målgrupper": "Forskningsorganisasjon"}, {}, [])
    e = match_funding.eligibility(build_calls.build_call(raw_call("5", plain)), person("Førsteamanuensis"))
    assert e["status"] == "no_restriction_found"  # shown as "check the official requirements"


# ---------------------------------------------------------------- matching
def test_recency_weighting_favours_current_work():
    w = match_funding.recency_weights(np.array([2026, 2023, 2020, 2027]), reference_year=2026)
    assert w[0] == 1 and w[3] == 1
    assert abs(w[1] - 0.5) < 1e-9 and w[2] < w[1]
    # A researcher whose topic changed: three 2020 papers on X weigh less than one 2026 paper on Y.
    assert 3 * w[2] < w[0]


def test_relevance_is_absolute():
    lo, hi = config.FUNDING_MATCH["similarity"]
    r = match_funding.relevance(np.array([[lo - 0.1], [lo], [(lo + hi) / 2], [hi + 0.1]]))
    assert list(r[:, 0]) == [0, 0, pytest.approx(0.5), 1]


def test_title_terms_drop_generic_words():
    call = {"fields": {"title": {"v": {"nb": "Næringsrettet kvanteteknologi", "en": "Industry-oriented Quantum Technology"}}}}
    terms = match_funding.title_terms(call)
    assert "quantum" in terms
    assert "technology" not in terms and "industry" not in terms


def test_title_terms_prefer_english_title():
    # Papers are mostly in English: a Norwegian title word ("helse") rarely matches.
    both = {"fields": {"title": {"v": {"nb": "Pilot Helse trinn 1", "en": "Pilot Health Phase 1"}}}}
    assert "helse" not in match_funding.title_terms(both)
    nb_only = {"fields": {"title": {"v": {"nb": "Kvanteteknologi", "en": None}}}}
    assert match_funding.title_terms(nb_only) == ["kvanteteknologi"]


def test_ai_profile_aspects_use_topics_and_skip_partner_requirements():
    call = {"fields": {"title": {"v": {"en": "Pilot Health"}}, "summary": {"v": None}, "themes": {"v": None}}}
    profile = {"profile": {
        "disciplines": [{"path": ["Digital health"], "level": "primary"}],
        "topics": [{"path": ["Digital health", "Remote care", "Home hospital"], "basis": "explicit", "evidence": "x"}],
        "technologies": ["Digital follow-up solutions"],
        "contributing_expertise": ["Wearable sensors and activity recognition"],
        "competencies": [
            {"name": "Health technology R&D", "kind": "core", "rationale": "r", "evidence": ""},
            {"name": "Company partner", "kind": "mandatory_partner", "rationale": "r", "evidence": ""},
            {"name": "Nice extra", "kind": "optional", "rationale": "r", "evidence": ""}],
        "methods": ["Pilot testing"], "application_domains": ["Home hospital"],   # duplicate label
    }}
    scope, aspects = match_funding.call_aspects(call, profile)
    assert scope.startswith("Pilot Health. Digital health") and "Home hospital" in scope
    kinds = {a["label"]: a["kind"] for a in aspects}
    assert kinds == {"Home hospital": "topic", "Health technology R&D": "core",
                     "Digital follow-up solutions": "technology",
                     "Wearable sensors and activity recognition": "expertise", "Pilot testing": "complementary"}
    assert [a["weight"] for a in aspects] == sorted((a["weight"] for a in aspects), reverse=True)


def test_corrections_and_editorials_are_not_evidence():
    assert not match_funding.is_evidence({"type": "Erratum", "title": "x"})
    assert not match_funding.is_evidence({"type": "Article", "title": "Corrigendum to 'A study'"})
    assert match_funding.is_evidence({"type": "Article", "title": "Seafood trade"})


def test_admin_sentences_are_not_aspects():
    call = build_calls.build_call(raw_call("6", tibi_page("X", {}, {}, [("Om utlysningen", [(
        "Tematiske føringer",
        "<ul><li>Prosjekter innen havbruk, fiskehelse og fôrutvikling for laks og andre arter.</li>"
        "<li>All informasjon om utlysningen finnes på hjemmesiden til partnerskapet.</li></ul>")])])))
    _, aspects = match_funding.call_aspects(call, None)
    labels = " ".join(a["label"] for a in aspects)
    assert "havbruk" in labels and "hjemmesiden" not in labels


# ------------------------------------------------------- AI output checking
def test_unverifiable_ai_facts_are_dropped_or_downgraded():
    source = "Prosjektleder må ha avlagt doktorgrad. Søknaden skal inneholde en datahåndteringsplan."
    profile = {
        "topics": [{"path": ["A"], "basis": "explicit", "evidence": "dette står ikke i teksten"}],
        "competencies": [{"name": "x", "kind": "core", "rationale": "", "evidence": "må ha avlagt doktorgrad"}],
        "fields": {
            "data_management": {"value": "Plan required", "status": "explicit",
                                "evidence": "Søknaden skal inneholde en datahåndteringsplan"},
            "cofunding": {"value": "50 %", "status": "explicit", "evidence": "50 prosent egenfinansiering"},
        },
    }
    out = profile_calls.verify(profile, source)
    assert out["topics"][0]["basis"] == "interpretation"
    assert out["competencies"][0]["verified"] is True
    assert out["fields"]["data_management"]["status"] == "explicit"
    assert out["fields"]["cofunding"]["status"] == "not_specified"  # invented quote -> not stored


def test_ai_answer_is_normalised_to_allowed_values_and_known_fields():
    out = profile_calls.normalise({
        "disciplines": [{"path": ["A"], "level": "main"}],
        "topics": [{"path": ["A"], "basis": "maybe", "evidence": ""}],
        "competencies": [{"name": "x", "kind": "essential", "rationale": "", "evidence": ""}],
        "fields": [{"key": "cofunding", "value": "50 %", "status": "explicit", "evidence": "q"},
                   {"key": "cofunding", "value": "other", "status": "explicit", "evidence": "q"},
                   {"key": "deadline", "value": "2030-01-01", "status": "explicit", "evidence": "q"}],
    })
    assert out["disciplines"][0]["level"] == "secondary" and out["topics"][0]["basis"] == "interpretation"
    assert out["competencies"][0]["kind"] == "optional"
    assert out["fields"]["cofunding"]["value"] == "50 %"           # first answer kept
    assert "deadline" not in out["fields"]                          # not an AI field: ignored
    assert set(out["fields"]) == set(profile_calls.AI_FIELDS)
    assert profile_calls.schema()["properties"]["fields"]["type"] == "array"  # small grammar


def test_ai_values_never_overwrite_stated_values():
    call = {"fields": {"deadline": build_calls.field("2026-05-27"),
                       "cofunding": build_calls.missing(),
                       "funding_rate": build_calls.field({"nb": "tekst"}, m="section"),
                       "url": build_calls.field({"nb": "https://x"})}}
    export_funding.merge_ai(call, {"profile": {"fields": {
        "deadline": {"value": "2030-01-01", "status": "explicit", "evidence": "q"},
        "cofunding": {"value": "50 %", "status": "explicit", "evidence": "q"},
        "funding_rate": {"value": "up to 50 %", "status": "explicit", "evidence": "q"}}}})
    assert call["fields"]["deadline"]["v"] == "2026-05-27"
    assert call["fields"]["cofunding"]["m"] == "ai"
    assert call["fields"]["funding_rate"]["v"] == {"nb": "tekst"} and call["fields"]["funding_rate"]["ai"]["v"] == "up to 50 %"


# ---------------------------------------------------------- encrypted export
def test_encryption_round_trip_and_password_not_in_file():
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt = b"0123456789abcdef"
    blob = export_funding.encrypt(b'{"calls": []}', export_funding.derive_key("Correct-Horse-1", salt), salt)
    assert "Correct-Horse-1" not in json.dumps(blob)
    d = lambda k: base64.b64decode(blob[k] if k == "data" else blob["kdf"]["salt"] if k == "salt" else blob["cipher"]["iv"])
    key = hashlib.pbkdf2_hmac("sha256", b"Correct-Horse-1", d("salt"), blob["kdf"]["iterations"], dklen=32)
    assert gzip.decompress(AESGCM(key).decrypt(d("iv"), d("data"), None)) == b'{"calls": []}'
    wrong = hashlib.pbkdf2_hmac("sha256", b"wrong", d("salt"), blob["kdf"]["iterations"], dklen=32)
    with pytest.raises(Exception):
        AESGCM(wrong).decrypt(d("iv"), d("data"), None)


def test_split_keeps_every_call_field_and_match():
    def field(v):
        return {"v": v, "s": "explicit"}
    calls = [{"id": f"eu-T{i}", "source": "eu", "fields": {"title": field({"en": f"T{i}"}), "status": field("open"),
                                                         "research_scope": field({"en": "long text"}),
                                                         "documents": field([])},
              "profile": {"topics": []}, "history": [{"k": 1}], "aspects": [], "review": []} for i in range(40)]
    data = {"meta": {}, "calls": calls, "matches": {"eu-T1": [{"id": "1", "score": 0.1}]}}
    index, shards = export_funding.split(data)
    assert len(shards) == export_funding.DETAIL_SHARDS and index["matches"] == data["matches"]
    assert [c["id"] for c in index["calls"]] == [c["id"] for c in calls]
    for orig, c in zip(calls, index["calls"]):
        d = shards[c["d"]][c["id"]]
        assert set(c["fields"]) == {"title", "status"} and set(d["fields"]) == {"research_scope", "documents"}
        assert {**c["fields"], **d["fields"]} == orig["fields"]
        assert d["profile"] == orig["profile"] and d["history"] == orig["history"] and "profile" not in c
        assert c["aspects"] == [] and c["d"] == export_funding.shard_of(c["id"])


def test_export_refuses_licensed_fields():
    with pytest.raises(SystemExit):
        export_funding.check_policy('{"abstract": "x"}')


# --------------------------------------------------------------------- web
def test_funding_ui_strings_exist_in_both_languages():
    en = json.loads((ROOT / "web/src/i18n/en.json").read_text(encoding="utf-8"))
    nb = json.loads((ROOT / "web/src/i18n/nb.json").read_text(encoding="utf-8"))
    files = ["web/src/funding.ts", "web/src/components/funding.tsx", "web/src/views/Funding.tsx",
             "web/src/views/Call.tsx", "web/src/views/Profile.tsx", "web/src/app.tsx"]
    used = set()
    for f in files:
        used |= set(re.findall(r'\bt\("([a-zA-Z.]+)"', (ROOT / f).read_text(encoding="utf-8")))
    used = {k for k in used if k.startswith(("f.", "fld.", "nav."))}
    assert used, "no keys found"
    assert not used - en.keys() and not used - nb.keys(), (used - en.keys()) | (used - nb.keys())
    fields = {k for grp in re.findall(r'\["[a-z]+", \[([^\]]+)\]\]', (ROOT / "web/src/views/Call.tsx").read_text(encoding="utf-8"))
              for k in re.findall(r'"([a-z_]+)"', grp)}
    assert fields and all(f"fld.{k}" in en and f"fld.{k}" in nb for k in fields)


def test_short_uis_record_does_not_flag_experienced_call():
    """The first UiS paper is not the first paper: a researcher recruited from elsewhere
    can have a short UiS record and still meet 'at least six years since the doctorate'."""
    page = tibi_page("Forskerprosjekt for erfarne forskere (FRIPRO)", {"Målgrupper": "Forskningsorganisasjon"}, {}, [
        ("Hvem kan delta i prosjektet?", [("Prosjektleder",
          "<ul><li>Erfaring: Du må ha godkjent doktorgrad, og det må ha gått minst seks år.</li></ul>")])])
    call = build_calls.build_call(raw_call("9", page))
    recent = person("Professor", config.REFERENCE_YEAR - 2)
    assert match_funding.eligibility(call, recent)["status"] == "no_restriction_found"


# ------------------------------------------------------------ notification
def test_telegram_message_is_skipped_without_setup_and_never_raises(monkeypatch):
    import notify
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert notify.send("x") is None
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:secret-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    sent = {}

    class Reply:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, *a): return b'{"ok": true}'

    def fake(url, body, timeout):
        sent.update(url=url, body=body)
        return Reply()
    monkeypatch.setattr(notify.urllib.request, "urlopen", fake)
    assert notify.send("Weekly update OK") is None
    assert b"chat_id=42" in sent["body"] and b"Weekly+update+OK" in sent["body"]

    def down(*a, **k):
        raise OSError("https://api.telegram.org/bot123:secret-token/sendMessage unreachable")
    monkeypatch.setattr(notify.urllib.request, "urlopen", down)
    error = notify.send("x")
    assert error and "secret-token" not in error  # the token is never logged
