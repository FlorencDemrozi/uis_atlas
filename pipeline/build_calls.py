#!/usr/bin/env python3
"""
Stage 2c – Turn the collected RCN pages into structured funding call records.

Input:  config.RAW_RCN/calls/*.json, config.RAW_RCN/sync_status.json,
        config/funding_overrides.json (manual corrections)
Output: config.CALLS          one record per call (see below)
        config.CALLS_HISTORY  append-only list of detected changes per call

Every field follows the field list agreed with the project owner (groups A–F:
general, financial, project, eligibility, evaluation, resources) and is stored as
  {"v": value, "s": status, "src": location, "url": source, "ev": evidence,
   "c": confidence, "m": method}
  status:     "explicit" (stated by RCN), "inferred" (derived by a stated rule),
              "not_specified" (RCN does not say) – never guessed
  method:     "metadata" (RCN's structured fields), "section" (the official text
              passage under that heading), "rule" (deterministic inference),
              "manual" (config/funding_overrides.json)
Text fields hold the official passage in Norwegian and English ({"nb", "en"}).
AI-condensed values (profile_calls.py) are added later next to these, never
over them. No LLM is used here: dates, amounts and URLs are parsed directly.
"""
import hashlib
import json
import re
from datetime import date, datetime

import config
import rcn

CALLS_DIR = config.RAW_RCN / "calls"
FUNDER = {"nb": "Norges forskningsråd", "en": "Research Council of Norway"}

# Sections of the call text, recognised by their heading (Norwegian or English).
SECTION_FIELDS = {
    "purpose": ["formål", "purpose", "hvorfor vi", "why we", "utlysningens tema"],
    "thematic": ["tematisk", "thematic"],
    "structural": ["strukturelle", "structural"],
    "delimitations": ["avgrensning", "delimitation"],
    "priorities": ["prioritering", "prioritisation", "prioritization"],
    "applicants": ["prosjektansvarlig", "project owner", "hvem kan søke", "who is eligible",
                   "who can apply"],
    "pi": ["prosjektleder", "project manager"],
    "partners": ["samarbeidspartner", "collaborating partner", "andre aktører", "other actors"],
    "rd_providers": ["fou-leverandør", "fou leverandør", "r&d provider"],
    "international": ["utenlandske", "foreign"],
    "subcontractors": ["underleverand", "subcontractor"],
    "funding_scope": ["omfanget av støtten", "scope of support", "støttesats", "statsstøtte",
                      "state aid", "tilgjengelige midler", "available funding", "hva kan du søke",
                      "rammer"],
    "funding_conditions": ["forutsetninger for tildeling", "conditions for funding"],
    "mobility": ["utenlands- og gjeste", "research stays abroad"],
    "evaluation": ["vurdering", "assessment", "evaluation"],
    "procedure": ["behandlingsprosedyre", "administrative procedure", "søknadsprosess", "prosedyre"],
    "ethics": ["etikk", "ethic"],
    "if_granted": ["dersom dere får", "dersom du får", "if you are granted", "rapportering"],
    "related": ["relaterte utlysninger", "related call"],
    "timeline": ["tidsplan", "timeline", "foreløpig kunngjøring", "planlagte utlysninger"],
}

# The agreed field list. Each text field is filled from these sections.
TEXT_FIELDS = {
    # B financial
    "funding_rate": ["funding_scope"],
    "funding_restrictions": ["funding_conditions", "delimitations"],
    # C project
    "research_scope": ["thematic", "purpose"], "structural_requirements": ["structural"],
    # D eligibility
    "eligible_applicants": ["applicants"], "pi_requirements": ["pi"],
    "partner_requirements": ["partners", "rd_providers"], "international_rules": ["international"],
    "subcontracting": ["subcontractors"], "mobility": ["mobility"],
    # E evaluation and application
    "evaluation_criteria": ["evaluation"], "priorities": ["priorities"],
    "procedure": ["procedure"], "ethics": ["ethics"], "if_granted": ["if_granted"],
}

# Fields only an AI reading (or a person) can fill; "not_specified" until then.
AI_ONLY_FIELDS = [
    "eligible_costs", "cofunding", "trl", "deliverables", "expected_impact", "career_stage", "nationality_residency",
    "consortium_size", "mandatory_partners", "industry_public_participation", "application_limits",
    "evaluation_weights", "required_documents", "data_management", "open_science",
]

# Funding schemes -> research orientation (deterministic rule, shown as inferred).
ORIENTATION = [
    (r"forskerprosjekt|fripro|banebrytende|toppforsk|unge forskertalent|grunnforskning", "fundamental"),
    (r"kompetanse- og samarbeid|samarbeidsprosjekt|forskning for anvendelse|forskning for økt kunnskap",
     "applied"),
    (r"kommersialisering|innovasjonsprosjekt|innovasjon i|skattefunn|pilot", "innovation"),
    (r"koordinerings|støtteaktivitet|arrangement|nettverk|registrering", "support"),
    (r"senter|centre|infrastruktur", "centre_infrastructure"),
]

CHANGE_KEYS = ["status", "deadline", "preliminary_deadline", "full_proposal_deadline", "opening_date",
               "min_amount", "max_amount", "total_budget", "target_groups", "updated"]


def field(v, s="explicit", src=None, url=None, ev=None, c="high", m="metadata") -> dict:
    return {"v": v, "s": s, "src": src, "url": url, "ev": ev, "c": c, "m": m}


def missing() -> dict:
    return field(None, "not_specified", c=None, m=None)


def deadline_kind(label: str) -> str | None:
    l = label.lower()
    if re.search(r"åpner|åpen for|active|opens", l):
        return "opening_date"
    if re.search(r"skisse|pre-?\s?propos|noi\b|trinn 1|notice of intent", l):
        return "preliminary_deadline"
    if re.search(r"full|invit|trinn 2|hovedfrist for de", l):
        return "full_proposal_deadline"
    if re.search(r"frist|deadline|stenger|closes|submission|søknad", l):
        return "deadline"
    return None


def status_of(listing: dict, meta: dict) -> str:
    s = listing["status"].lower()
    if listing["timeframe"] == "completed" or "gjennomført" in s or "resultat" in s:
        return "closed"
    if "planlagt" in s or "kommer" in listing["date"].lower():
        return "planned"
    return "open"


# Matched on any level of the heading path (the whole section belongs to the field);
# all other fields match only a short (sub)heading, so a long heading such as
# "Assessment of whether the application satisfies the ... structural guidelines"
# is not taken for "Structural guidelines".
WHOLE_SECTION_KEYS = {"evaluation", "procedure", "if_granted"}
MAX_HEADING = 60


def match_sections(secs: list[dict], keys: list[str]) -> list[dict]:
    out = []
    for s in secs:
        leaf = s["path"][-1].lower()
        for k in keys:
            if k in WHOLE_SECTION_KEYS:
                hit = any(p in " > ".join(s["path"]).lower() for p in SECTION_FIELDS[k])
            else:
                hit = len(leaf) <= MAX_HEADING and any(p in leaf for p in SECTION_FIELDS[k])
            if hit:
                out.append(s)
                break
    return out


def uis_can_apply(groups: str | None, applicants: list[dict]) -> tuple[bool | None, str | None, str]:
    """Can a research organisation such as UiS be the project owner?

    The project-owner requirements decide when RCN states them ("the Project Owner
    must be registered in the Register of Business Enterprises" -> no, even if
    research organisations are a target group as partners). Otherwise the target
    groups decide, with lower confidence."""
    text = "\n".join(s["text"] for s in applicants).lower()
    if text:
        if re.search(r"forskningsorganisasjon|research organisation|universitet|universit(y|ies)", text):
            return True, text[:400], "medium"
        if re.search(r"foretaksregister|enhetsregister|register of business|bedrift|company|companies|"
                     r"kommune|municipalit|offentlig virksomhet|public (sector )?(entity|enterprise)", text):
            return False, text[:400], "medium"
    if groups:
        return bool(re.search(r"forskningsorganisasjon", groups, re.I)), groups, "low"
    return None, None, "low"


def passage(sec_nb: list[dict], sec_en: list[dict], keys: list[str], url_nb: str, url_en: str | None) -> dict:
    nb, en = match_sections(sec_nb, keys), match_sections(sec_en, keys)
    if not nb and not en:
        return missing()
    text = lambda ss: "\n\n".join(s["text"] for s in ss) or None
    src = " > ".join((en or nb)[0]["path"])
    return field({"nb": text(nb), "en": text(en)}, "explicit", src, url_en if en else url_nb,
                 None, "high", "section")


def doc_links(secs: list[dict]) -> list[dict]:
    out, seen = [], set()
    for s in secs:
        for link in s["links"]:
            url = link["url"]
            if (not url or url in seen or url.startswith("mailto:") or "/Download" in url
                    or not link["text"]):
                continue
            seen.add(url)
            t = (link["text"] + " " + url).lower()
            kind = ("template" if re.search(r"mal\b|template|skjema", t)
                    else "faq" if re.search(r"faq|spørsmål og svar|questions", t)
                    else "guidelines" if re.search(r"retningslinj|guideline|veiled|guide|krav|regler", t)
                    else "projects" if "prosjektbanken" in t
                    else "other")
            out.append({"text": link["text"], "url": url, "kind": kind, "src": " > ".join(s["path"])})
    return out


def build_call(raw: dict) -> dict:
    listing, nb, en = raw["listing"], raw["nb"], raw.get("en") or {}
    url_nb, url_en = raw["url"], raw.get("en_url")
    meta_nb, meta_en = rcn.metadata(nb), rcn.metadata(en)
    sec_nb, sec_en = rcn.sections(nb), rcn.sections(en)
    timeline = rcn.timeline(nb)
    by = rcn.byline_dates(nb)
    f: dict[str, dict] = {}
    review: list[str] = []
    meta_field = lambda v, label: field(v, src=label, url=url_nb)

    # ---- A. general
    cid = f"rcn-{raw['id']}"
    f["call_id"] = field(raw["id"], src="RCN page id", url=url_nb)
    f["title"] = field({"nb": rcn.clean(nb.get("title")) or listing["title"],
                        "en": rcn.clean(en.get("title")) or None}, src="page title", url=url_nb)
    f["funder"] = field(FUNDER, src="source website", url=rcn.BASE_URL)
    scheme = meta_nb.get("Finansieringsordning")
    f["scheme"] = (meta_field({"nb": scheme, "en": meta_en.get("Financial scheme")}, "Finansieringsordning")
                   if scheme else missing())
    prog = meta_nb.get("Program")
    f["programme"] = meta_field({"nb": prog, "en": meta_en.get("Programme") or meta_en.get("Program")},
                                "Program") if prog else missing()
    f["url"] = field({"nb": url_nb, "en": url_en}, src="page address", url=url_nb)
    pre_nb, pre_en = rcn.preamble(nb), rcn.preamble(en)
    f["summary"] = (field({"nb": pre_nb or None, "en": pre_en or None}, src="introduction", url=url_nb,
                          m="section") if pre_nb or pre_en else missing())
    desc = passage(sec_nb, sec_en, ["purpose"], url_nb, url_en)
    if desc["s"] == "not_specified":  # simple layout: the whole description
        whole = lambda ss: "\n\n".join(s["text"] for s in ss) or None
        if sec_nb or sec_en:
            desc = field({"nb": whole(sec_nb), "en": whole(sec_en)}, src="description", url=url_en or url_nb,
                         m="section")
    f["description"] = desc
    status = status_of(listing, meta_nb)
    f["status"] = field(status, "explicit", "call list status", config.RCN_LIST_URL.format(timeframe=0),
                        listing["status"])

    deadlines: dict[str, list] = {}
    for label, text in meta_nb.items():
        kind = deadline_kind(label)
        if kind:
            deadlines.setdefault(kind, []).append((label, text))
    for t in timeline:
        kind = deadline_kind(t["label"])
        if kind == "opening_date" and "opening_date" not in deadlines:
            deadlines["opening_date"] = [(t["label"], t["date"])]
    rolling = "løpende" in listing["date"].lower() or any(
        "løpende" in (text or "").lower() for items in deadlines.values() for _, text in items)
    for kind in ("opening_date", "deadline", "preliminary_deadline", "full_proposal_deadline"):
        items = deadlines.get(kind, [])
        dates = [(label, rcn.parse_date(text) if not re.match(r"\d{4}-", text) else text, text)
                 for label, text in items]
        dates = [d for d in dates if d[1]]
        if dates:
            label, iso, text = dates[0]
            tentative = "foreløpig" in label.lower() or "preliminary" in label.lower()
            f[kind] = field(iso, src=label, url=url_nb, ev=text, c="medium" if tentative else "high")
            if tentative:
                review.append(f"{kind}: marked as preliminary by RCN")
        else:
            f[kind] = missing()
    if f["deadline"]["s"] == "not_specified" and f["full_proposal_deadline"]["s"] == "explicit":
        f["deadline"] = dict(f["full_proposal_deadline"], s="inferred", c="medium",
                             ev="no single deadline; using the full-proposal deadline")
    f["rolling"] = field(rolling, src="call list date", url=url_nb, ev=listing["date"] or None)
    f["published"] = field(by["published"], src="byline", url=url_nb) if "published" in by else missing()
    f["updated"] = field(by["updated"], src="byline", url=url_nb) if "updated" in by else missing()

    # ---- B. financial
    scale = meta_nb.get("Støttegrenser")
    money = rcn.parse_money(scale)
    for key, part in (("min_amount", "min"), ("max_amount", "max")):
        f[key] = field(money[part], src="Støttegrenser", url=url_nb, ev=scale) if part in money else missing()
    if "value" in money:  # a single figure without "up to": treat as the maximum, flag it
        f["max_amount"] = field(money["value"], "inferred", "Støttegrenser", url_nb, scale, "medium", "rule")
        review.append(f"funding scale is a single figure: {scale}")
    total = meta_nb.get("Antatt tilgjengelige midler")
    budget = rcn.parse_money(total)
    total_value = budget.get("value") or budget.get("max")
    f["total_budget"] = (field(total_value, src="Antatt tilgjengelige midler", url=url_nb, ev=total)
                         if total_value else missing())
    cur = money.get("currency") or budget.get("currency")
    f["currency"] = field(cur, src="amount text", url=url_nb, ev=scale or total) if cur else missing()
    for key in ("funding_rate", "funding_restrictions"):
        f[key] = passage(sec_nb, sec_en, TEXT_FIELDS[key], url_nb, url_en)

    # ---- C. project characteristics
    dur = meta_nb.get("Prosjektvarighet")
    months = rcn.parse_months(dur)
    for key, part in (("min_duration_months", "min"), ("max_duration_months", "max")):
        f[key] = field(months[part], src="Prosjektvarighet", url=url_nb, ev=dur) if part in months else missing()
    for key, labels in (("earliest_start", ["tidligste tillatte prosjektstart"]),
                        ("latest_start", ["seneste tillatte prosjektstart"]),
                        ("latest_end", ["seneste tillatte prosjektslutt"])):
        hit = next(((label, text) for label, text in meta_nb.items() if label.lower() in labels), None)
        iso = rcn.parse_date(hit[1]) if hit else None
        if not iso:
            t = next((t for t in timeline if t["label"].lower() in labels), None)
            hit, iso = ((t["label"], t["date"]), t["date"]) if t else (None, None)
        f[key] = field(iso, src=hit[0], url=url_nb, ev=hit[1]) if iso else missing()
    for key in ("research_scope", "structural_requirements"):
        f[key] = passage(sec_nb, sec_en, TEXT_FIELDS[key], url_nb, url_en)
    basis = " ".join(filter(None, [scheme, listing["group"], listing["title"]])).lower()
    orient = next((o for pat, o in ORIENTATION if re.search(pat, basis)), None)
    f["orientation"] = (field(orient, "inferred", "funding scheme", url_nb, scheme or listing["group"],
                              "medium", "rule") if orient else missing())
    trl = sorted({int(n) for s in sec_nb + sec_en for n in re.findall(r"\bTRL\s*-?\s*(\d)", s["text"])})
    f["trl"] = (field(f"TRL {trl[0]}–{trl[-1]}" if len(trl) > 1 else f"TRL {trl[0]}", "explicit",
                      "call text", url_nb, None, "medium", "section") if trl else missing())

    # ---- D. eligibility
    groups = meta_nb.get("Målgrupper") or meta_nb.get("Hvem retter utlysningen seg mot") or meta_nb.get("Hvem kan søke")
    groups_en = (meta_en.get("Target groups") or meta_en.get("Who is the call for proposal aimed at")
                 or meta_en.get("Who is eligible to apply"))
    split = lambda s: [x.strip() for x in re.split(r",|;", s or "") if x.strip()]
    f["target_groups"] = (field({"nb": split(groups), "en": split(groups_en)}, src="Målgrupper", url=url_nb)
                          if groups else missing())
    applicants_nb = match_sections(sec_nb, ["applicants"])
    can, basis_text, conf = uis_can_apply(groups, applicants_nb)
    f["uis_can_apply"] = (field(can, "inferred", " > ".join(applicants_nb[0]["path"]) if applicants_nb else "Målgrupper",
                                url_nb, basis_text, conf, "rule") if can is not None else missing())
    for key in ("eligible_applicants", "pi_requirements", "partner_requirements", "international_rules",
                "subcontracting", "mobility"):
        f[key] = passage(sec_nb, sec_en, TEXT_FIELDS[key], url_nb, url_en)
    f["international"] = field(bool(listing["international"]) or "internasjonal" in (scheme or "").lower(),
                               "explicit" if listing["international"] else "inferred", "call list",
                               url_nb, scheme, "medium", "metadata" if listing["international"] else "rule")

    # ---- E. evaluation and application
    for key in ("evaluation_criteria", "priorities", "procedure", "ethics", "if_granted"):
        f[key] = passage(sec_nb, sec_en, TEXT_FIELDS[key], url_nb, url_en)
    for key in AI_ONLY_FIELDS:
        f.setdefault(key, missing())

    # ---- F. resources
    themes = meta_nb.get("Aktuelle temaområder") or meta_nb.get("Portefølje")
    themes_en = meta_en.get("Relevant thematic areas for this call") or meta_en.get("Portfolio")
    f["themes"] = (field({"nb": split(themes), "en": split(themes_en)}, src="Aktuelle temaområder", url=url_nb)
                   if themes else missing())
    docs = doc_links(sec_en or sec_nb)
    f["documents"] = (field(docs, src="links in the call text", url=url_en or url_nb, m="section")
                      if docs else missing())

    if status == "open" and f["deadline"]["v"] and not rolling and f["deadline"]["v"][:10] < date.today().isoformat():
        review.append("listed as open but the deadline has passed")
    if status != "closed" and not rolling and f["deadline"]["s"] == "not_specified":
        review.append("no deadline found")
    if scale and not money:
        review.append(f"funding scale not understood: {scale}")

    text_all = "\n".join(s["text"] for s in (sec_en or sec_nb))
    return {
        "id": cid, "source": "rcn", "listing_group": listing["group"], "tags": listing["tags"],
        "fetched": raw["fetched"], "fields": f, "review": review,
        "sections": {"nb": sec_nb, "en": sec_en},
        "content_hash": hashlib.sha1(text_all.encode("utf-8")).hexdigest(),
    }


def comparable(call: dict, key: str):
    v = call["fields"].get(key, {}).get("v")
    return json.dumps(v, ensure_ascii=False, sort_keys=True)


def apply_overrides(call: dict, overrides: dict) -> None:
    for key, o in overrides.get(call["id"], {}).get("fields", {}).items():
        call["fields"][key] = field(o.get("v"), o.get("s", "explicit"), "manual correction",
                                    o.get("url"), o.get("note"), "high", "manual")


def main() -> None:
    overrides = (json.loads(config.FUNDING_OVERRIDES.read_text(encoding="utf-8")).get("calls", {})
                 if config.FUNDING_OVERRIDES.exists() else {})
    old = {c["id"]: c for c in json.loads(config.CALLS.read_text(encoding="utf-8"))["calls"]} \
        if config.CALLS.exists() else {}
    history = json.loads(config.CALLS_HISTORY.read_text(encoding="utf-8")) if config.CALLS_HISTORY.exists() else {}
    status = (json.loads((config.RAW_RCN / "sync_status.json").read_text(encoding="utf-8"))
              if (config.RAW_RCN / "sync_status.json").exists() else {})
    listed = set(status.get("calls_listed", []))
    today = datetime.now().isoformat(timespec="seconds")

    calls = []
    for path in sorted((config.RAW_RCN / "calls").glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        call = build_call(raw)
        if overrides.get(call["id"], {}).get("exclude"):
            continue
        apply_overrides(call, overrides)
        call["listed"] = raw["id"] in listed if listed else True
        prev = old.get(call["id"])
        changes = history.setdefault(call["id"], [])
        if prev is None:
            changes.append({"date": today, "field": "new", "old": None, "new": None})
        else:
            for key in CHANGE_KEYS:
                a, b = comparable(prev, key), comparable(call, key)
                if a != b:
                    changes.append({"date": today, "field": key, "old": prev["fields"].get(key, {}).get("v"),
                                    "new": call["fields"].get(key, {}).get("v")})
            if prev.get("content_hash") != call["content_hash"]:
                changes.append({"date": today, "field": "text", "old": None, "new": None})
            if prev.get("listed") and not call["listed"]:
                changes.append({"date": today, "field": "unlisted", "old": None, "new": None})
        calls.append(call)

    config.CALLS.write_text(json.dumps({
        "generated": today, "sync": {k: status.get(k) for k in ("last_attempt", "last_success", "errors")},
        "calls": calls}, ensure_ascii=False), encoding="utf-8")
    config.CALLS_HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=1), encoding="utf-8")
    n_status = {s: sum(c["fields"]["status"]["v"] == s for c in calls) for s in ("open", "planned", "closed")}
    print(f"Calls: {len(calls)} ({n_status}); {sum(bool(c['review']) for c in calls)} flagged for review.")


if __name__ == "__main__":
    main()
