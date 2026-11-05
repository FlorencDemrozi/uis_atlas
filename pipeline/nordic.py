"""NordForsk and Nordic Energy Research calls -> funding call records (same field
model as RCN calls and EU topics; see callfields.py).

Pure functions on the files collect_nordic.py stores, so they can be tested on
saved records without network access.

NordForsk states each call's opening date and deadline as structured data, so the
status follows from the dates. Nordic Energy Research marks each item "Open" or
"Closed" and "Call" or "Tender"; tenders are procurement and are left out. Its
deadline is only in the call text ("the deadline for submissions is 12 May at
13:00"); it is read from there and, when the year is missing, the year is taken
from the publication date (stored as "inferred" with that basis).
Both funders write in English only. Nothing is filled in when the funder does not say it.
"""
import hashlib
import re
from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

import config
import rcn
from callfields import doc_links, field, missing

FUNDERS = {
    "nordforsk": {"nb": "NordForsk", "en": "NordForsk"},
    "nordicenergy": {"nb": "Nordisk energiforskning", "en": "Nordic Energy Research"},
}

# Every field a call record carries (the union of the RCN and EU field sets), so the
# later stages can read any of them; those not set below stay "not_specified".
ALL_FIELDS = [
    "call_id", "title", "funder", "scheme", "programme", "programme_part", "parent_call", "action_type", "url",
    "summary", "description", "status", "opening_date", "deadline", "preliminary_deadline",
    "full_proposal_deadline", "cutoff_dates", "deadline_model", "rolling", "published", "updated",
    "min_amount", "max_amount", "total_budget", "expected_grants", "currency", "funding_model", "funding_rate",
    "funding_restrictions", "min_duration_months", "max_duration_months", "earliest_start", "latest_start",
    "latest_end", "research_scope", "structural_requirements", "expected_impact", "orientation", "open_field",
    "trl", "target_groups", "uis_can_apply", "norway_eligible", "institution_level", "eligible_applicants",
    "pi_requirements", "partner_requirements", "international_rules", "subcontracting", "mobility",
    "international", "evaluation_criteria", "priorities", "procedure", "ethics", "if_granted",
    "eligible_costs", "cofunding", "deliverables", "career_stage", "nationality_residency", "consortium_size",
    "mandatory_partners", "industry_public_participation", "application_limits", "evaluation_weights",
    "required_documents", "data_management", "open_science", "themes", "documents",
]

# Section headings (lower case) -> field; the first matching rule wins.
SECTION_RULES = [
    (r"expected outcome|expected impact", "expected_impact"),
    (r"funding partners|participating partners|participating countries", "international_rules"),
    (r"aim|thematic|scope|research objective|background|objective|focus", "research_scope"),
    (r"eligib|consorti|participants|research team|who can apply", "eligible_applicants"),
    (r"funding|financial|budget", "funding_rate"),
    (r"evaluation|assessment|criteria", "evaluation_criteria"),
    (r"decision|how to apply|application process|submission|timeline", "procedure"),
]

# A sentence saying universities / research organisations may apply.
UNIVERSITY = re.compile(r"universit|research organi[sz]ation|research institution|higher education", re.I)
APPLY = re.compile(r"eligible|can apply|may apply|apply for|main applicant|project (leader|owner)|lead applicant|"
                   r"open to|applicants? must", re.I)

MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}
DATE_IN_TEXT = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + "|".join(MONTHS) + r")\b(?:,?\s+(\d{4}))?", re.I)
DEADLINE_WORDS = re.compile(r"deadline|closes|close on|submission|submit|apply by|no later than", re.I)
NOT_THE_DEADLINE = re.compile(r"question|webinar|info(rmation)? (session|meeting)|notification|decision|"
                              r"start(ing)? date|project start|results|initiate|must (start|begin|end)|"
                              r"end no later|project period|completed by", re.I)
ROLLING = re.compile(r"budget (is|has been) (exhausted|used)|until further notice|on a rolling basis|"
                     r"continuously|no (fixed )?deadline", re.I)


# ----------------------------------------------------------------- helpers
def text_of(s: str | None) -> str:
    return rcn.clean((s or "").replace(" ", " "))


def unwrap(url: str | None) -> str | None:
    """Outlook "safelinks" wrappers (pasted into some call pages) -> the real address."""
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.netloc.endswith("safelinks.protection.outlook.com"):
        return (parse_qs(parsed.query).get("url") or [url])[0]
    return url


def sections(html: str | None, root: str, site: str) -> list[dict]:
    """Page body (WordPress block markup) -> [{"path", "text", "links"}]."""
    html = re.sub(r"<!--.*?-->", "", html or "", flags=re.S).replace(" ", " ")
    html = re.sub(r'href="/(?!/)', f'href="{site}/', html)
    secs = rcn._split_headings([root], html)
    for s in secs:
        for link in s["links"]:
            link["url"] = unwrap(link["url"])
    return secs


def pick(secs: list[dict], key: str) -> list[dict]:
    out = []
    for s in secs:
        if len(s["path"]) < 2:
            continue
        heading = s["path"][-1].lower()
        if next((k for pat, k in SECTION_RULES if re.search(pat, heading)), None) == key:
            out.append(s)
    return out


def section_field(secs: list[dict], url: str) -> dict:
    if not secs:
        return missing()
    return field({"en": "\n\n".join(s["text"] for s in secs)}, "explicit", " > ".join(secs[0]["path"]), url,
                 None, "high", "section")


def uis_can_apply(secs: list[dict], url: str) -> dict:
    """True when a sentence of the call says universities / research organisations may
    apply (eligibility sections first). Never False: the calls rarely exclude them
    explicitly, and a missing statement is shown as "not specified"."""
    for s in pick(secs, "eligible_applicants") + secs:
        for sentence in re.split(r"(?<=[.!?])\s+|\n", s["text"]):
            if UNIVERSITY.search(sentence) and APPLY.search(sentence):
                return field(True, "inferred", " > ".join(s["path"]), url, sentence.strip()[:400], "medium", "rule")
    return missing()


def to_iso(day: str, month: str, year: str | None, published: str) -> tuple[str | None, bool]:
    """('YYYY-MM-DD', year_inferred). A date without a year is the first such date
    on or after the publication date."""
    pub = date.fromisoformat(published[:10])
    try:
        if year:
            return date(int(year), MONTHS[month.lower()], int(day)).isoformat(), False
        d = date(pub.year, MONTHS[month.lower()], int(day))
        if d < pub:
            d = date(pub.year + 1, d.month, d.day)
        return d.isoformat(), True
    except ValueError:
        return None, False


def text_deadline(text: str, published: str) -> tuple[str, str, bool] | None:
    """(date, sentence, year inferred) of the application deadline stated in the text:
    the latest date in a sentence that says "deadline" or, if there is none, in a
    sentence about submission (never one about questions, webinars, decisions or
    the project period)."""
    sentences = [s for s in re.split(r"(?<=[.!?])\s+|\n", text)
                 if DEADLINE_WORDS.search(s) and not NOT_THE_DEADLINE.search(s) and DATE_IN_TEXT.search(s)]
    preferred = [s for s in sentences if re.search(r"deadline", s, re.I)] or sentences
    best = None
    for sentence in preferred:
        for m in DATE_IN_TEXT.finditer(sentence):
            iso, inferred = to_iso(m.group(1), m.group(2), m.group(3), published)
            if iso and (best is None or iso > best[0]):
                best = (iso, sentence.strip()[:300], inferred)
    return best


def base_record(source: str, ident: str, url: str, secs: list[dict], fetched: str, group: str,
                tags: list[str], review: list[str], f: dict) -> dict:
    for key in ALL_FIELDS:
        f.setdefault(key, missing())
    text_all = "\n".join(s["text"] for s in secs)
    return {
        "id": f"{source}-{ident}", "source": source, "family": source, "listing_group": group, "tags": tags,
        "fetched": fetched, "fields": f, "review": review, "sections": {"nb": [], "en": secs},
        "content_hash": hashlib.sha1(text_all.encode("utf-8")).hexdigest(),
    }


def common_text_fields(f: dict, secs: list[dict], url: str) -> None:
    for key in ("research_scope", "expected_impact", "eligible_applicants", "international_rules", "funding_rate",
                "evaluation_criteria", "procedure"):
        f[key] = section_field(pick(secs, key), url)
    if f["research_scope"]["s"] == "not_specified" and secs:  # no recognisable parts: the whole text
        f["description"] = field({"en": "\n\n".join(s["text"] for s in secs)}, "explicit", "call text", url,
                                 None, "high", "section")
    f["uis_can_apply"] = uis_can_apply(secs, url)
    f["international"] = field(True, "inferred", "funder", url, "Nordic research cooperation", "high", "rule")
    trl = sorted({int(n) for s in secs for n in re.findall(r"\bTRL\s*-?\s*(\d)", s["text"])})
    f["trl"] = (field(f"TRL {trl[0]}–{trl[-1]}" if len(trl) > 1 else f"TRL {trl[0]}", "explicit", "call text", url,
                      None, "medium", "section") if trl else missing())


# --------------------------------------------------------------- NordForsk
def nordforsk_names(rel: dict | None, included: dict) -> list[str]:
    data = (rel or {}).get("data")
    items = data if isinstance(data, list) else [data] if data else []
    out = []
    for x in items:
        a = (included.get(x["id"]) or {}).get("attributes") or {}
        name = text_of(a.get("name") or a.get("title"))
        if name:
            out.append(name)
    return out


def build_nordforsk(node: dict, included: dict, fetched: str, today: str | None = None) -> dict:
    today = today or date.today().isoformat()
    a, rel = node["attributes"], node.get("relationships") or {}
    nid = str(a["drupal_internal__nid"])
    url = config.NORDFORSK_SITE + ((a.get("path") or {}).get("alias") or f"/node/{nid}")
    secs = sections((a.get("body") or {}).get("value"), "Call text", config.NORDFORSK_SITE)
    f: dict[str, dict] = {}
    review: list[str] = []
    meta = lambda v, src: field(v, src=src, url=url)

    f["call_id"] = meta(nid, "NordForsk page id")
    f["title"] = meta({"en": text_of(a.get("title"))}, "page title")
    f["funder"] = field(FUNDERS["nordforsk"], src="source website", url=config.NORDFORSK_CALLS_PAGE)
    programmes = nordforsk_names(rel.get("field_program"), included)
    f["programme"] = meta({"en": "; ".join(programmes)}, "programme") if programmes else missing()
    apply_url = unwrap((a.get("field_cta") or {}).get("uri"))
    f["url"] = field({"en": url}, src="page address", url=url)
    summary = text_of((a.get("field_summary") or {}).get("value") or a.get("field_subtitle"))
    f["summary"] = meta({"en": summary}, "summary") if summary else missing()

    dates = a.get("field_call_date") or {}
    opening, deadline = (dates.get("value") or "")[:10] or None, (dates.get("end_value") or "")[:10] or None
    f["opening_date"] = meta(opening, "call dates") if opening else missing()
    f["deadline"] = field(deadline, src="call dates", url=url, ev=dates.get("end_value")) if deadline else missing()
    if not deadline:
        status, ev = "open" if opening and opening <= today else "planned", "no deadline given"
        review.append("no deadline found")
    elif deadline < today:
        status, ev = "closed", f"deadline {deadline} has passed"
    elif opening and opening > today:
        status, ev = "planned", f"opens {opening}"
    else:
        status, ev = "open", f"open {opening or '?'} – {deadline}"
    f["status"] = field(status, "inferred", "call dates", url, ev, "high", "rule")
    f["rolling"] = meta(False, "call dates")
    f["published"] = meta(a["created"][:10], "publication date") if a.get("created") else missing()
    f["updated"] = meta(a["changed"][:10], "last changed") if a.get("changed") else missing()

    common_text_fields(f, secs, url)
    themes = nordforsk_names(rel.get("field_topic"), included)
    f["themes"] = meta({"en": themes}, "topics") if themes else missing()
    docs = doc_links(secs)
    if apply_url and apply_url.startswith(("https://", "http://")):  # the application link comes first
        docs = [{"text": text_of((a.get("field_cta") or {}).get("title")) or "Call text and application",
                 "url": apply_url, "kind": "guidelines", "src": "call page"}] + [d for d in docs if d["url"] != apply_url]
    f["documents"] = field(docs, src="links in the call text", url=url, m="section") if docs else missing()
    if apply_url and "funding.nordforsk.org" not in apply_url:
        review.append(f"applications go through a partner's site: {urlparse(apply_url).netloc}")
    return base_record("nordforsk", nid, url, secs, fetched, programmes[0] if programmes else "", themes, review, f)


# ---------------------------------------------------- Nordic Energy Research
def build_ner(item: dict, terms: dict, fetched: str, today: str | None = None) -> dict:
    today = today or date.today().isoformat()
    ident = str(item["id"])
    url = item.get("link") or config.NER_CALLS_PAGE
    names = lambda tax: [terms.get(tax, {}).get(str(i)) for i in item.get(tax) or [] if terms.get(tax, {}).get(str(i))]
    secs = sections((item.get("content") or {}).get("rendered"), "Call text", config.NER_SITE)
    whole = "\n".join(s["text"] for s in secs)
    f: dict[str, dict] = {}
    review: list[str] = []
    meta = lambda v, src: field(v, src=src, url=url)
    published = (item.get("date") or fetched)[:10]

    f["call_id"] = meta(ident, "page id")
    f["title"] = meta({"en": text_of(re.sub(r"<[^>]+>", "", (item.get("title") or {}).get("rendered") or ""))},
                      "page title")
    f["funder"] = field(FUNDERS["nordicenergy"], src="source website", url=config.NER_CALLS_PAGE)
    f["url"] = field({"en": url}, src="page address", url=url)
    excerpt = text_of(re.sub(r"<[^>]+>", " ", (item.get("excerpt") or {}).get("rendered") or ""))
    excerpt = re.sub(r"\s*(\[…\]|\[&hellip;\]|…)$", "", excerpt)
    if excerpt:
        f["summary"] = meta({"en": excerpt}, "excerpt")
    elif secs:
        f["summary"] = field({"en": secs[0]["text"][:450]}, "explicit", "call text", url, None, "high", "section")

    listed = (names("current_status") or ["?"])[0].lower()
    rolling = bool(ROLLING.search(whole))
    found = text_deadline(whole, published)
    if found:
        iso, sentence, inferred = found
        f["deadline"] = (field(iso, "inferred", "call text", url, f"{sentence} (year taken from the publication "
                               f"date {published})", "medium", "rule") if inferred
                         else field(iso, "explicit", "call text", url, sentence, "high", "section"))
    f["rolling"] = field(rolling, "explicit" if rolling else "inferred", "call text", url,
                         (ROLLING.search(whole).group(0) if rolling else None), "medium", "section" if rolling else "rule")
    status = "open" if listed == "open" else "closed"
    f["status"] = field(status, "explicit", "status on the funder's site", url, listed.capitalize())
    if status == "open" and found and not rolling and found[0] < today:
        f["status"] = field("closed", "inferred", "deadline", url,
                            f"listed as open, but the deadline ({found[0]}) has passed", "high", "rule")
        review.append("listed as open by the funder, but the deadline has passed")
    if status == "open" and not found and not rolling:
        review.append("no deadline found")
    f["published"] = meta(published, "publication date")
    f["updated"] = meta(item["modified"][:10], "last changed") if item.get("modified") else missing()

    common_text_fields(f, secs, url)
    themes = names("topics")
    f["themes"] = meta({"en": themes}, "topics") if themes else missing()
    docs = doc_links(secs)
    f["documents"] = field(docs, src="links in the call text", url=url, m="section") if docs else missing()
    return base_record("nordicenergy", ident, url, secs, fetched, "", themes, review, f)


def is_tender(item: dict, terms: dict) -> bool:
    kinds = [terms.get("funding_type", {}).get(str(i), "") for i in item.get("funding_type") or []]
    return any(k.lower() == "tender" for k in kinds)


# ------------------------------------------------------------------ select
def records(nordforsk: dict | None, nordicenergy: dict | None, today: str | None = None) -> list[dict]:
    """Every call to show: open and planned ones, plus those closed within
    config.NORDIC_CLOSED_MONTHS (by deadline, or publication date when there is none)."""
    today = today or date.today().isoformat()
    cutoff = (date.fromisoformat(today) - timedelta(days=round(30.4 * config.NORDIC_CLOSED_MONTHS))).isoformat()
    out = []
    if nordforsk:
        for node in nordforsk.get("calls") or []:
            if (node.get("attributes") or {}).get("status") is False:  # unpublished
                continue
            out.append(build_nordforsk(node, nordforsk.get("included") or {}, nordforsk["fetched"], today))
    if nordicenergy:
        terms = nordicenergy.get("terms") or {}
        for item in nordicenergy.get("items") or []:
            if not is_tender(item, terms):
                out.append(build_ner(item, terms, nordicenergy["fetched"], today))

    def recent(c: dict) -> bool:
        f = c["fields"]
        if f["status"]["v"] != "closed":
            return True
        return (f["deadline"]["v"] or f["published"]["v"] or "") >= cutoff
    return [c for c in out if recent(c)]
