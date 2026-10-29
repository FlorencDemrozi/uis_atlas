"""EU Funding & Tenders topics -> funding call records (same field model as RCN calls).

Pure functions on the records collect_eu.py stores, so they can be tested on saved
topics without network access. The hierarchy Programme → Work programme part →
Call → Topic is kept explicitly; the topic is the unit that is matched.

Every value comes from the portal's structured data or the official topic text.
Programme-level rules (e.g. Norway's participation, standard Horizon Europe
consortium and funding-rate rules) are stored as "inferred" with their basis.
Nothing is filled in when the portal does not say it.
"""
import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone

import config
import rcn
from callfields import doc_links, field, missing

FUNDER = {"nb": "Den europeiske union", "en": "European Union"}
SOURCE_PAGE = "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/calls-for-proposals"
HORIZON_ANNEXES = ("https://ec.europa.eu/info/funding-tenders/opportunities/docs/2021-2027/horizon/wp-call/"
                   "2026-2027/wp-15-general-annexes_horizon-2026-2027_en.pdf")

# Programmes Norway takes part in, so Norwegian organisations can be funded (subject
# to topic restrictions). Only well-documented cases; every other programme is
# "not determined" and shown as "check". (code, basis, confidence)
NORWAY_PROGRAMMES = {
    "HORIZON": ("Norway is associated to Horizon Europe: Norwegian entities can participate and "
                "coordinate on the same terms as EU Member States.", "high"),
    "DIGITAL": ("Norway takes part in the Digital Europe Programme through the EEA Agreement.", "medium"),
    "EU4H": ("Norway takes part in EU4Health through the EEA Agreement.", "medium"),
    "ERASMUS2027": ("Norway takes part in Erasmus+ through the EEA Agreement.", "medium"),
    "CREA2027": ("Norway takes part in Creative Europe through the EEA Agreement.", "medium"),
}
NORWAY_SOURCE = ("https://ec.europa.eu/info/funding-tenders/opportunities/docs/2021-2027/common/guidance/"
                 "list-3rd-country-participation_horizon-euratom_en.pdf")

# Topic text that limits participation to EU Member States (Associated Countries,
# Norway included, may then be excluded): the researcher should check.
RESTRICTED = re.compile(
    r"article\s+22\s*\(\s*[56]\s*\)|article\s+12\s*\(\s*[56]\s*\)|"
    r"(restricted|limited) to (legal )?entities established in (eu )?member states|"
    r"only (legal )?entities established in (eu )?member states|member states only", re.I)

# Programme families for the website filters (the first matching rule wins).
FAMILIES = [
    ("erc", r"^ERC-"), ("msca", r"^HORIZON-MSCA-"), ("eic", r"^HORIZON-EIC-"),
    ("missions", r"^HORIZON-MISS-"),
    ("partnerships", r"^(HORIZON|DIGITAL)-(JU|EUROHPC|KDT|EIT)-|^HORIZON-EUROHPC|^HORIZON-EIT-"),
    ("horizon", r"^HORIZON-"),
]

# Calls open to every research field: an exact official phrase, or the programme
# rule for the bottom-up ERC / MSCA / EIC Pathfinder Open calls.
OPEN_PHRASE = re.compile(r"any field of (science|research)|no predefined thematic priorities|"
                         r"all fields of research can be considered|any research disciplines", re.I)
OPEN_RULES = [
    (r"^ERC-\d{4}-(STG|COG|ADG|SYG)$", "ERC frontier-research grants have no predefined topics: "
                                       "proposals in any field of research are eligible."),
    (r"^HORIZON-MSCA-\d{4}-(PF|DN|SE)-", "MSCA Postdoctoral Fellowships, Doctoral Networks and Staff "
                                         "Exchanges are bottom-up: any research field may be proposed."),
    (r"^HORIZON-EIC-\d{4}-PATHFINDEROPEN", "EIC Pathfinder Open has no predefined thematic priorities."),
]
# EIC Accelerator funds companies (SMEs, small mid-caps); a university cannot apply.
COMPANY_ONLY = re.compile(r"^HORIZON-EIC-\d{4}-ACCELERATOR")
# Calls an institution applies for as a whole (co-funded fellowship programmes,
# European Researchers' Night): listed, but not matched to individual researchers.
INSTITUTION_LEVEL = [
    (r"^HORIZON-MSCA-\d{4}-COFUND-", "MSCA COFUND co-funds a doctoral or fellowship programme run by an "
                                     "institution: the institution applies, not an individual researcher."),
    (r"^HORIZON-MSCA-\d{4}-CITIZENS-", "European Researchers' Night: public outreach events organised by an "
                                       "institution, not a research project."),
]
ERC_WP = "https://erc.europa.eu/manage-your-project/documents-and-forms"
MSCA_WP = "https://marie-sklodowska-curie-actions.ec.europa.eu/actions"
# Who takes part, and in which role, for the bottom-up ERC and MSCA actions (programme
# rules from the ERC and MSCA work programmes; topic texts rarely restate them).
# (identifier pattern, rule text, source, role offered to UiS researchers)
ROLE_RULES = [
    (r"^ERC-\d{4}-STG$", "ERC Starting Grant: the principal investigator is 2–7 years past the PhD on "
                         "1 January of the call year (extensions possible, e.g. for parental leave).",
     ERC_WP, "pi_candidate"),
    (r"^ERC-\d{4}-COG$", "ERC Consolidator Grant: the principal investigator is more than 7 and up to 12 years "
                         "past the PhD on 1 January of the call year (extensions possible, e.g. for parental leave).",
     ERC_WP, "pi_candidate"),
    (r"^ERC-\d{4}-ADG$", "ERC Advanced Grant: the principal investigator has a track record of significant "
                         "research achievements in the last 10 years.", ERC_WP, "pi_candidate"),
    (r"^ERC-\d{4}-SYG$", "ERC Synergy Grant: two to four principal investigators, each with a doctorate.",
     ERC_WP, "pi_candidate"),
    (r"^HORIZON-MSCA-\d{4}-PF-", "MSCA Postdoctoral Fellowship: the fellow (a researcher with a PhD, at most "
                                 "8 years after it) applies with a host organisation; UiS staff take part as "
                                 "the fellow's supervisor.", MSCA_WP, "supervisor"),
    (r"^HORIZON-MSCA-\d{4}-DN-", "MSCA Doctoral Network: the network recruits doctoral candidates; UiS staff take "
                                 "part as supervisors in the consortium.", MSCA_WP, "supervisor"),
    (r"^HORIZON-MSCA-\d{4}-SE-", "MSCA Staff Exchanges: research, technical and administrative staff at any career "
                                 "stage are seconded between partner organisations.", MSCA_WP, "secondment"),
]

# Short codes of the type of action, from the portal's typeOfAction label.
ACTION_CODE = re.compile(r"^(?:HORIZON|DIGITAL|EURATOM|EDF|LIFE|CEF|CERV|CREA|ERASMUS|EU4H|SMP|ESF|ISF|JUST|"
                         r"RFCS|PPPA|I3|JTM|EUAF|EP|SOCPL|EUBA|[A-Z0-9]+)-(?:JU-|TMA-)?([A-Za-z0-9-]+?)\s")

ORIENTATION = [  # (type-of-action code pattern, orientation)
    (r"^ERC", "fundamental"), (r"^(RIA|RA)$", "applied"), (r"^(IA|PCP|PPI|EIC-ACC)", "innovation"),
    (r"^CSA$", "support"),
]
STANDARD_RULES = {  # Horizon Europe General Annexes B (consortium) and D (funding rate)
    "RIA": ("At least three independent legal entities, each established in a different EU Member State "
            "or Associated Country, at least one of them in a Member State.", "100% of eligible costs"),
    "IA": ("At least three independent legal entities, each established in a different EU Member State "
           "or Associated Country, at least one of them in a Member State.",
           "70% of eligible costs (100% for non-profit legal entities)"),
    "CSA": ("At least one legal entity established in an EU Member State or Associated Country.",
            "100% of eligible costs"),
}

# Condition headings (numbered, wording varies by programme) -> fields.
CONDITION_FIELDS = [
    (r"admissibility", "required_documents"),
    (r"eligible countries|^\d\.\s*eligibility$", "international_rules"),
    (r"other eligib", "partner_requirements"),
    (r"award criteria", "evaluation_criteria"),
    (r"submission and evaluation process|indicative timeline", "procedure"),
    (r"legal and financial set-?up", "if_granted"),
    (r"specific conditions", "funding_restrictions"),
]
DESCRIPTION_FIELDS = [
    (r"expected outcome|expected impact", "expected_impact"),
    (r"^scope|specific challenge|^objective", "research_scope"),
]


# ----------------------------------------------------------------- values
def to_date(x) -> str | None:
    """Portal dates: epoch milliseconds at Brussels midnight (stored in UTC, so 22:00
    or 23:00 the day before) or text such as '19 March 2024'. Returns 'YYYY-MM-DD'."""
    if x is None or x == "":
        return None
    s = str(x).strip()
    if s.lstrip("-").isdigit():
        dt = datetime.fromtimestamp(int(s) / 1000, tz=timezone.utc) + timedelta(hours=2)
        return dt.date().isoformat()
    if re.match(r"\d{4}-\d{2}-\d{2}", s):
        return (datetime.fromisoformat(s[:19]) + timedelta(hours=2)).date().isoformat() if "T" in s else s[:10]
    for fmt in ("%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def html_sections(fragment: str | None, root: str, kind_marker: bool = False) -> list[dict]:
    """Official HTML -> [{"path", "text", "links"}]. Topic descriptions mark their parts
    with <p class="topicdescriptionkind">Scope:</p>; those become headings."""
    html = fragment or ""
    if kind_marker:
        html = re.sub(r'<p class="topicdescriptionkind">(.*?):?\s*</p>', r"<h3>\1</h3>", html, flags=re.S)
    return rcn._split_headings([root], html)


def opening_text(text: str, limit: int = 450) -> str:
    """The start of an official passage, lines kept, cut at a word near `limit`
    ("Project results are expected to contribute to: • … • …")."""
    out = ""
    for line in text.split("\n"):
        out = f"{out}\n{line}" if out else line
        if len(out) >= limit:
            break
    return out if len(out) <= limit + 150 else out[:limit].rsplit(" ", 1)[0] + " …"


def heading_of(section: dict) -> str:
    return section["path"][-1].strip().rstrip(":").lower() if len(section["path"]) > 1 else ""


def pick_sections(secs: list[dict], rules: list[tuple[str, str]], key: str) -> list[dict]:
    pats = [p for p, k in rules if k == key]
    out = []
    for s in secs:
        h = heading_of(s)
        if h and any(re.search(p, h) for p in pats):
            out.append(s)
    return out


def section_field(secs: list[dict], url: str) -> dict:
    if not secs:
        return missing()
    text = "\n\n".join(s["text"] for s in secs)
    return field({"en": text}, "explicit", " > ".join(secs[0]["path"]), url, None, "high", "section")


def sentence(text: str, pat: re.Pattern) -> str | None:
    for s in re.split(r"(?<=[.!?])\s+|\n", text or ""):
        if pat.search(s):
            return s.strip()[:400]
    return None


# ------------------------------------------------------------ normalising
def from_listing(meta: dict, names: dict[str, str]) -> dict:
    """A topic record built from the search index alone (cascade calls, or a topic
    whose page could not be read). The index carries the same texts as JSON strings."""
    first = lambda k: (meta.get(k) or [None])[0]
    loads = lambda k: json.loads(first(k)) if first(k) else None
    prog = first("frameworkProgramme")
    return {
        "identifier": first("identifier"), "title": first("title"),
        "callIdentifier": first("callIdentifier"), "callTitle": first("callTitle"),
        "description": first("descriptionByte") or first("description"),
        "conditions": first("topicConditions"),
        "budgetOverviewJSONItem": loads("budgetOverview") or {},
        "actions": loads("actions") or [],
        "frameworkProgramme": {"id": prog, "abbreviation": None, "description": names.get(str(prog))},
        "programmeDivision": [{"id": d, "abbreviation": None, "description": names.get(str(d))}
                              for d in meta.get("programmeDivision") or [] if names.get(str(d))],
        "publicationDateLong": first("startDate"),
        "listing_only": True,
    }


def division_path(topic: dict) -> list[str]:
    """Programme divisions from broad to specific (by abbreviation depth when present)."""
    divs = [d for d in topic.get("programmeDivision") or [] if d.get("description")]
    prog = (topic.get("frameworkProgramme") or {}).get("description")
    if all(d.get("abbreviation") for d in divs):
        divs.sort(key=lambda d: d["abbreviation"].count(".") + len(d["abbreviation"]) / 1000)
    return [d["description"] for d in divs if d["description"] != prog]


def role_rule(identifier: str) -> tuple[str, str, str] | None:
    """(rule text, source, role offered) for ERC / MSCA actions, else None."""
    return next(((text, src, role) for pat, text, src, role in ROLE_RULES if re.search(pat, identifier, re.I)), None)


def family_of(identifier: str) -> str:
    return next((fam for fam, pat in FAMILIES if re.search(pat, identifier, re.I)), "other_eu")


def actions_of(topic: dict) -> list[dict]:
    return [a for a in topic.get("actions") or [] if isinstance(a, dict)]


def action_types(topic: dict) -> list[str]:
    return [t.get("typeOfAction", "") for a in actions_of(topic) for t in a.get("types") or [] if t.get("typeOfAction")]


def action_code(type_of_action: str) -> str | None:
    m = ACTION_CODE.match(type_of_action + " ")
    return m.group(1).upper() if m else None


def budget_rows(topic: dict) -> list[dict]:
    """Budget lines of this topic (the overview covers the whole call)."""
    overview = topic.get("budgetOverviewJSONItem") or {}
    if isinstance(overview, str):
        overview = json.loads(overview or "{}")
    rows = []
    for lines in (overview.get("budgetTopicActionMap") or {}).values():
        for line in lines if isinstance(lines, list) else []:
            if isinstance(line, dict) and (line.get("action") or "").split(" - ")[0].strip() == topic["identifier"]:
                rows.append(line)
    return rows


def deadlines(topic: dict, rows: list[dict]) -> tuple[list[str], str | None, str | None]:
    """(all deadlines sorted, deadline model, opening date)."""
    dates, opening, model = set(), None, None
    for a in actions_of(topic) + rows:
        for d in a.get("deadlineDates") or []:
            if to_date(d):
                dates.add(to_date(d))
        opening = opening or to_date(a.get("plannedOpeningDate"))
        model = model or a.get("deadlineModel")
    return sorted(dates), model, opening


# ------------------------------------------------------------------ build
def build_topic(raw: dict, names: dict[str, str], today: str | None = None) -> dict:
    """One funding record per topic, with the RCN field model plus EU fields."""
    today = today or date.today().isoformat()
    listing = raw["listing"]
    meta = listing.get("metadata") or {}
    topic = raw.get("details") or from_listing(meta, names)
    topic.setdefault("identifier", raw["id"])
    ident = topic["identifier"]
    url = config.EU_PORTAL_URL.format(ident) if listing.get("type") == "1" else (listing.get("url") or SOURCE_PAGE)
    f: dict[str, dict] = {}
    review: list[str] = []
    meta_field = lambda v, src: field(v, src=src, url=url)

    desc = html_sections(topic.get("description"), "Topic description", kind_marker=True)
    cond = html_sections(topic.get("conditions"), "Topic conditions")
    prog = topic.get("frameworkProgramme") or {}
    prog_code = prog.get("abbreviation") or next((k for k, v in names.items() if v == prog.get("description")
                                                  and not k.isdigit()), None)
    path = division_path(topic)
    types = action_types(topic)
    codes = sorted({c for c in map(action_code, types) if c})
    mgas = sorted({m.get("description", "") for a in actions_of(topic) for t in a.get("types") or []
                   for m in t.get("typeOfMGA") or [] if m.get("description")})

    # ---- A. general: the hierarchy Programme → Work programme part → Call → Topic
    f["call_id"] = meta_field(ident, "topic identifier")
    f["title"] = meta_field({"en": rcn.clean(topic.get("title")) or listing.get("title") or ident}, "topic title")
    f["funder"] = field(FUNDER, src="Funding & Tenders Portal", url=SOURCE_PAGE)
    f["programme"] = meta_field({"en": prog.get("description")}, "framework programme") if prog.get("description") \
        else missing()
    f["programme_part"] = meta_field({"en": " > ".join(path)}, "programme division") if path else missing()
    call_id, call_title = topic.get("callIdentifier"), rcn.clean(topic.get("callTitle"))
    f["parent_call"] = (meta_field({"en": f"{call_title} ({call_id})" if call_title and call_title != call_id
                                    else call_id}, "call") if call_id else missing())
    f["scheme"] = (meta_field({"en": "; ".join(sorted({re.sub(r"^\S+\s+", "", t).strip() for t in types}))},
                              "type of action") if types else missing())
    f["action_type"] = meta_field(codes, "type of action") if codes else missing()
    f["url"] = field({"en": url}, src="portal page", url=url)
    whole = "\n\n".join(s["text"] for s in desc)
    outcome = pick_sections(desc, DESCRIPTION_FIELDS, "expected_impact")
    lead = (outcome or pick_sections(desc, DESCRIPTION_FIELDS, "research_scope") or desc)
    f["summary"] = (field({"en": opening_text(lead[0]["text"])}, "explicit", " > ".join(lead[0]["path"]),
                          url, None, "high", "section") if lead else missing())
    has_parts = bool(outcome or pick_sections(desc, DESCRIPTION_FIELDS, "research_scope"))
    f["description"] = (missing() if has_parts or not whole
                        else field({"en": whole}, "explicit", "topic description", url, None, "high", "section"))

    # ---- status and dates
    rows = budget_rows(topic)
    dates, model, opening = deadlines(topic, rows)
    model = model or (meta.get("deadlineModel") or [None])[0]
    if not dates and to_date(listing.get("deadline")):  # records without action data
        dates = [to_date(listing["deadline"])]
    status =listing.get("status") if listing.get("status") in ("open", "planned", "closed") else "closed"
    f["status"] = field(status, "explicit", "portal status", url, listing.get("status"))
    continuous = model == "continuous"
    if status != "closed" and dates and not continuous and dates[-1] < today:
        f["status"] = field("closed", "inferred", "deadlines", url,
                            f"listed as {status}, but the last deadline ({dates[-1]}) has passed", "high", "rule")
        review.append(f"listed as {status} by the portal, but all deadlines have passed")
    if re.search(r"cancel+ed", ident + " " + (topic.get("title") or ""), re.I):
        f["status"] = field("closed", "explicit", "topic identifier", url, "cancelled", "high", "rule")
        review.append("cancelled")
    f["opening_date"] = meta_field(opening, "planned opening date") if opening else missing()
    for k in ("deadline", "preliminary_deadline", "full_proposal_deadline"):
        f[k] = missing()
    if model == "two-stage" and len(dates) >= 2:
        f["preliminary_deadline"] = meta_field(dates[0], "first-stage deadline")
        f["full_proposal_deadline"] = meta_field(dates[-1], "second-stage deadline")
        f["deadline"] = field(dates[-1], "inferred", "second-stage deadline", url,
                              "two-stage topic; the final deadline is the second stage", "high", "metadata")
    elif dates:
        upcoming = [d for d in dates if d >= today]
        d = upcoming[0] if upcoming else dates[-1]
        f["deadline"] = meta_field(d, "next cut-off" if len(dates) > 1 else "deadline")
    f["cutoff_dates"] = meta_field(dates, "cut-off dates") if len(dates) > 1 and model != "two-stage" else missing()
    f["deadline_model"] = meta_field(model, "deadline model") if model else missing()
    f["rolling"] = meta_field(continuous, "deadline model")
    f["published"] = (meta_field(to_date(topic.get("publicationDateLong")), "publication date")
                      if to_date(topic.get("publicationDateLong")) else missing())
    f["updated"] = missing()

    # ---- B. financial (EU contribution, euro)
    total = round(max((sum(float(v or 0) for v in (r.get("budgetYearMap") or {}).values()) for r in rows),
                      default=0))
    mins = [r.get("minContribution") or 0 for r in rows if r.get("minContribution")]
    maxs = [r.get("maxContribution") or 0 for r in rows if r.get("maxContribution")]
    grants = max((r.get("expectedGrants") or 0 for r in rows), default=0)
    f["total_budget"] = meta_field(total, "topic budget") if total else missing()
    f["min_amount"] = meta_field(min(mins), "EU contribution per project (minimum)") if mins else missing()
    f["max_amount"] = meta_field(max(maxs), "EU contribution per project (maximum)") if maxs else missing()
    f["expected_grants"] = meta_field(grants, "indicative number of grants") if grants else missing()
    f["currency"] = meta_field("EUR", "budget overview") if total or mins or maxs else missing()
    f["funding_model"] = meta_field(mgas, "model grant agreement") if mgas else missing()
    rule = STANDARD_RULES.get(codes[0]) if prog_code == "HORIZON" and len(codes) == 1 \
        and types and not re.search(r"-JU-", types[0]) else None
    f["funding_rate"] = (field({"en": rule[1]}, "inferred", "Horizon Europe General Annex D", HORIZON_ANNEXES,
                               f"standard rule for {codes[0]} actions unless the topic conditions say otherwise",
                               "medium", "rule") if rule else missing())
    f["funding_restrictions"] = section_field(pick_sections(cond, CONDITION_FIELDS, "funding_restrictions"), url)

    # ---- C. project
    for k in ("min_duration_months", "max_duration_months", "earliest_start", "latest_start", "latest_end",
              "structural_requirements", "deliverables"):
        f[k] = missing()
    f["research_scope"] = section_field(pick_sections(desc, DESCRIPTION_FIELDS, "research_scope"), url)
    f["expected_impact"] = section_field(outcome, url)
    orient = next((o for pat, o in ORIENTATION if codes and re.search(pat, codes[0])), None)
    if re.search(r"-INFRA-", ident):
        orient = "centre_infrastructure"
    f["orientation"] = (field(orient, "inferred", "type of action", url, ", ".join(types) or ident, "medium", "rule")
                        if orient else missing())
    phrase = sentence(whole, OPEN_PHRASE)
    open_rule = next((basis for pat, basis in OPEN_RULES if re.search(pat, ident, re.I)), None)
    if phrase and not COMPANY_ONLY.search(ident):
        f["open_field"] = field(True, "explicit", "topic description", url, phrase, "high", "section")
    elif open_rule:
        f["open_field"] = field(True, "inferred", "programme rule", url, open_rule, "high", "rule")
    else:
        f["open_field"] = missing()
    trl = sorted({int(n) for n in re.findall(r"\bTRL\s*-?\s*(\d)", whole)})
    f["trl"] = (field(f"TRL {trl[0]}–{trl[-1]}" if len(trl) > 1 else f"TRL {trl[0]}", "explicit",
                      "topic description", url, None, "medium", "section") if trl else missing())

    # ---- D. eligibility
    cond_text = "\n".join(s["text"] for s in cond)
    norway = NORWAY_PROGRAMMES.get(prog_code or "")
    restricted = sentence(cond_text + "\n" + whole, RESTRICTED)
    if restricted:
        f["norway_eligible"] = field(None, "inferred", "topic conditions", url, restricted, "medium", "rule")
        review.append("participation restricted to some countries: check whether Norway is included")
    elif norway:
        f["norway_eligible"] = field(True, "inferred", "programme participation",
                                     NORWAY_SOURCE if prog_code == "HORIZON" else url, norway[0], norway[1], "rule")
    else:
        f["norway_eligible"] = missing()
    if COMPANY_ONLY.search(ident):
        f["uis_can_apply"] = field(False, "inferred", "programme rule", url,
                                   sentence(whole, re.compile(r"\bSMEs?\b|start-?ups?|compan", re.I))
                                   or "EIC Accelerator funds individual companies (SMEs and small mid-caps).",
                                   "high", "rule")
        f["target_groups"] = field({"en": ["Companies (start-ups, SMEs, small mid-caps)"]}, "inferred",
                                   "programme rule", url, None, "high", "rule")
    else:
        f["uis_can_apply"] = (field(True, "inferred", "programme participation", f["norway_eligible"]["url"],
                                    f["norway_eligible"]["ev"], f["norway_eligible"]["c"], "rule")
                              if f["norway_eligible"]["v"] is True else missing())
        f["target_groups"] = missing()
    for key in ("international_rules", "partner_requirements"):
        f[key] = section_field(pick_sections(cond, CONDITION_FIELDS, key), url)
    f["eligible_applicants"] = missing()
    role = role_rule(ident)
    f["pi_requirements"] = (field({"en": role[0]}, "inferred", "programme rule", role[1], role[0], "high", "rule")
                            if role else missing())
    inst = next((basis for pat, basis in INSTITUTION_LEVEL if re.search(pat, ident, re.I)), None)
    f["institution_level"] = (field(True, "inferred", "programme rule", url, inst, "high", "rule")
                              if inst else missing())
    f["consortium_size"] = (field({"en": rule[0]}, "inferred", "Horizon Europe General Annex B", HORIZON_ANNEXES,
                                  f"standard rule for {codes[0]} actions unless the topic conditions say otherwise",
                                  "medium", "rule") if rule else missing())
    f["international"] = field(True, "inferred", "funding programme", url, "EU programme", "high", "rule")
    for k in ("subcontracting", "mobility"):
        f[k] = missing()

    # ---- E. evaluation and application
    for key in ("evaluation_criteria", "procedure", "if_granted", "required_documents"):
        f[key] = section_field(pick_sections(cond, CONDITION_FIELDS, key), url)
    for k in ("priorities", "ethics"):
        f[k] = missing()

    # ---- F. resources
    f["themes"] = meta_field({"en": path[-2:]}, "programme division") if path else missing()
    docs = doc_links(cond)
    f["documents"] = field(docs, src="topic conditions", url=url, m="section") if docs else missing()

    if f["status"]["v"] != "closed" and not dates and not continuous:
        review.append("no deadline found")
    if topic.get("listing_only") and listing.get("type") == "1":
        review.append("topic page could not be read; text from the portal's search index")

    text_all = whole + "\n" + cond_text
    return {
        "id": f"eu-{ident}", "source": "eu", "family": family_of(ident), "listing_group": call_title or call_id or "",
        "tags": [], "fetched": raw["fetched"], "fields": f, "review": review,
        "sections": {"nb": [], "en": desc + cond},
        "content_hash": hashlib.sha1(text_all.encode("utf-8")).hexdigest(),
    }


def programme_names(records: list[dict]) -> dict[str, str]:
    """id -> name (and abbreviation -> name) for programmes and divisions, from topic
    pages, so records built from the search index alone still get names."""
    names: dict[str, str] = {}
    for r in records:
        t = r.get("details") or {}
        for d in [t.get("frameworkProgramme") or {}] + list(t.get("programmeDivision") or []):
            if d.get("id") and d.get("description"):
                names[str(d["id"])] = d["description"]
                if d.get("abbreviation"):
                    names[d["abbreviation"]] = d["description"]
    return names
