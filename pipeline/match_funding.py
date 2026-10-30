#!/usr/bin/env python3
"""
Stage 4c – Match UiS researchers to open and planned funding calls, and suggest
internal collaborators who complement them.

Input:  config.CALLS, config.CALL_PROFILES (optional), config.PROFILES,
        paper vectors from embed.py, papers in config.RAW_ATLAS
Output: config.FUNDING_MATCHES

Method (settings in config.FUNDING_MATCH; transparent and reproducible):
1. Each call is split into "aspects": the research topics, technologies,
   contributing expertise, competencies, methods and domains of its AI profile
   when one exists (partner requirements and optional extras are not research
   expertise and are left out), otherwise the thematic bullets and paragraphs
   of the official call text. A "scope" text (title, summary, themes, and the
   profile's disciplines and topics) describes the call as a whole.
2. Every recent paper (last config.ACTIVE_YEARS years) is compared with the
   scope and each aspect (same embedding model as the search, "query:" prefix
   for the call). Similarities are turned into a relevance of 0–1 relative to
   all UiS papers for that call, and weighted by recency (half-life
   recency_half_life_years).
3. Score = weights.scope × scope alignment (mean of the 3 most relevant papers)
         + weights.coverage × share of the call's aspects covered by a paper
         + weights.evidence × amount of relevant work (saturating with count)
   Category: High / Medium / Low by config thresholds. A ranking aid for one
   call – not a probability of funding. Besides the best overall matches, the
   researchers who best cover each aspect are always listed ("specialists"),
   so a technology expert is found for a call led by another field.
4. Eligibility is checked separately, only from conditions stated in the call
   text, and shown with the sentence it rests on. It never raises a score.
5. Collaborators: other UiS researchers whose papers cover aspects the matched
   researcher does not, preferring existing co-authors (verified by shared
   papers) and other departments. All are suggestions, not commitments.
"""
import json
import math
import re
import sys
from datetime import datetime

import numpy as np

import config
import embed
import eu

CFG = config.FUNDING_MATCH
# Administrative sentences say nothing about the science and are not used as aspects.
NOISE = re.compile(r"frist|deadline|søknad|proposal|application|webinar|registrer|register|kontakt|"
                   r"contact|budsjett|budget|\bkr\b|€|\bnok\b|eligib|apply|søke|informasjon|information|"
                   r"les mer|read more|https?://|hjemmeside|nettside|website|partnere fra|partners from|"
                   r"konsorti|consorti|land som deltar|countries|participating|samler nasjonale|"
                   r"national and regional|funding agenc|finansieringsorgan|matchmaking", re.I)
# Words too general to identify a call's topic (title keyword signal).
GENERIC = set((
    "research forskning project projects prosjekt prosjekter call calls utlysning support støtte innovation "
    "innovasjon industry industri næringsliv næringsrettet technology technologies teknologi teknologier "
    "development utvikling norwegian norsk norske norway norge national nasjonale nasjonal international "
    "internasjonal internasjonale new nye partnership partnerskap joint felles sector sektor sektoren public "
    "offentlig private oriented rettet based basert collaboration samarbeid cooperation knowledge kunnskap "
    "future fremtidens society samfunn societal challenges utfordringer solutions løsninger centre centres "
    "senter sentre network networks nettverk competence kompetanse grant funding finansiering membership "
    "medlemskap association european europeisk eu horizon horisont transnational phase stage trinn pilot "
    "researchers forskere forsker early tidlig career karriere experienced erfarne programme program "
    "quality kvalitet efficiency effektivitet renewal fornyelse projects areas area field fields studies "
    "and og for of i in on the to med til av en et som om fra ved under mellom with a an or 2025 2026 2027"
).split())


# ------------------------------------------------------------------ call side
def lang_text(v, lang="en"):
    if isinstance(v, dict):
        return v.get(lang) or v.get("nb") or v.get("en")
    return v


ASPECT_WEIGHTS = {"topic": 1.0, "core": 1.0, "scope": 1.0, "technology": 0.8, "expertise": 0.8,
                  "complementary": 0.6}


def call_aspects(call: dict, profile: dict | None) -> tuple[str, list[dict]]:
    f = call["fields"]
    title = lang_text(f["title"]["v"])
    themes = lang_text(f["themes"]["v"]) or []
    parts = [title, lang_text(f["summary"]["v"]), ", ".join(themes)]
    aspects = []
    if profile:
        p = profile["profile"]
        # RCN calls rarely fill summary and themes; without the profile the scope is the title
        # alone. EU topics have a full official summary: their scope stays official text, since
        # broad profile disciplines ("Machine learning") lifted too many general matches
        # (project owner, 2026-10-29).
        if call.get("source") != "eu":
            parts += [" > ".join(d["path"]) for d in p.get("disciplines", [])]
            parts += [t["path"][-1] for t in p.get("topics", []) if t["path"]]
        ai = lambda label, text, kind, evidence="": {"label": label, "text": text, "kind": kind,
                                                      "source": "ai", "evidence": evidence}
        for t in p.get("topics", []):
            if t["path"]:
                aspects.append(ai(t["path"][-1], " > ".join(t["path"]), "topic", t.get("evidence") or ""))
        for x in p.get("technologies", []):
            aspects.append(ai(x, x, "technology"))
        for x in p.get("contributing_expertise", []):
            aspects.append(ai(x, x, "expertise"))
        for c in p["competencies"]:
            # Required partners (a company, a hospital) and optional extras are not research expertise.
            if c["kind"] in ASPECT_WEIGHTS:
                aspects.append(ai(c["name"], f"{c['name']}: {c['rationale']}", c["kind"], c.get("evidence") or ""))
        for key in ("methods", "application_domains"):
            for x in p[key]:
                aspects.append(ai(x, x, "complementary"))
    else:
        passage = lang_text(f["research_scope"]["v"]) or lang_text(f["description"]["v"]) or ""
        seen = set()
        for line in passage.split("\n"):
            text = line.lstrip("• ").strip()
            words = text.split()
            # A line ending in ":" only introduces a list ("Projects should address the issues below:").
            if (not 5 <= len(words) <= 120 or NOISE.search(text) or text.lower() in seen
                    or text.endswith(":")):
                continue
            seen.add(text.lower())
            label = " ".join(words[:14]) + ("…" if len(words) > 14 else "")
            aspects.append({"label": label, "text": text, "kind": "scope", "source": "call_text",
                            "evidence": text if len(words) <= 60 else ""})
    seen, unique = set(), []
    for a in aspects:
        if a["label"].lower() not in seen:
            seen.add(a["label"].lower())
            unique.append(dict(a, weight=ASPECT_WEIGHTS[a["kind"]]))
    unique.sort(key=lambda a: -a["weight"])
    return ". ".join(filter(None, parts)), unique[:CFG["max_aspects"]]


# ------------------------------------------------------------ researcher side
POSITION_KINDS = [
    (r"^stipendiat", "phd"), (r"^postdoktor", "postdoc"), (r"em\.|pensjonert", "emeritus"),
    (r"\bii\b", "adjunct"), (r"ekstern|sensor|oppdragstaker", "external"),
    (r"^professor|^dosent", "professor"),
    (r"^førsteamanuensis|^forsker|^førstelektor|^universitetslektor|^universitetslærer", "faculty"),
]


def position_kind(r: dict) -> str | None:
    p = ((r.get("position") or {}).get("nb") or "").lower()
    if not p:
        return None
    return next((kind for pat, kind in POSITION_KINDS if re.search(pat, p)), "other")


def sentence_with(text: str, pattern: str) -> str | None:
    for s in re.split(r"(?<=[.!?])\s+|\n", text or ""):
        if re.search(pattern, s, re.I):
            return s.strip()[:400]
    return None


# ERC career limits, in years since the researcher's first paper in the atlas. The atlas
# has no PhD dates and the first paper often comes before the PhD, so upper limits get
# wide margins over the official windows (eu.ROLE_RULES). Lower limits need the full
# publication history (collect_scopus_authors.py; "full_record"): without it, papers
# from earlier employers are missing and a short record says little. All give "check".
ERC_STG_MAX_YEARS = 12
ERC_COG_YEARS = (7, 16)
ERC_ADG_MIN_YEARS = 10


def eu_role_eligibility(ident: str, kind: str | None, career: int | None,
                        full_record: bool = False) -> tuple[str, str] | None:
    """(status, reason) from the ERC / MSCA role rules, or None if nothing applies.
    Only the position (PhD candidate) is certain enough for "likely_ineligible"."""
    if re.match(r"ERC-", ident, re.I):
        if kind == "phd":
            return "likely_ineligible", "erc_doctorate"
        if re.search(r"-STG$", ident, re.I) and (kind in ("professor", "emeritus")
                                                  or (career is not None and career > ERC_STG_MAX_YEARS)):
            return "check", "erc_stg_window"
        if re.search(r"-COG$", ident, re.I) and career is not None and (
                career > ERC_COG_YEARS[1] or (full_record and career < ERC_COG_YEARS[0])):
            return "check", "erc_cog_window"
        if re.search(r"-ADG$", ident, re.I) and (
                kind == "postdoc" or (full_record and career is not None and career < ERC_ADG_MIN_YEARS)):
            return "check", "erc_adg_record"
    elif re.match(r"HORIZON-MSCA-\d{4}-(PF|DN)-", ident, re.I):
        if kind == "phd":
            return "likely_ineligible", "msca_supervisor"
        if kind == "postdoc":
            return "check", "msca_supervisor_postdoc"
    return None


def eligibility(call: dict, r: dict) -> dict:
    """{"status", "reason", "evidence"} from conditions stated in the call text."""
    f = call["fields"]
    # The project-manager requirements come first, so the quoted evidence is the rule itself.
    text = "\n".join(filter(None, [lang_text(f[k]["v"], lang) for k in ("pi_requirements", "eligible_applicants",
                                                                       "description", "summary")
                                   for lang in ("nb", "en")]
                         + [lang_text(f["title"]["v"], "nb"), lang_text(f["title"]["v"], "en")]))
    kind = position_kind(r)
    # Career age is estimated from the first paper in the atlas (there are no PhD dates).
    # Lower limits only once the full publication history is collected (Scopus author
    # metrics present): before that, papers from earlier employers are missing.
    career = config.REFERENCE_YEAR - r["first_year"] if r.get("first_year") else None
    full_record = bool(r.get("scopus_metrics"))
    out = lambda status, reason, ev=None: {"status": status, "reason": reason, "evidence": ev}
    if call.get("source") == "eu":
        # EU topics: can a Norwegian university take part at all? (eu.py, with its basis)
        norway = f.get("norway_eligible") or {}
        if f["uis_can_apply"]["v"] is False:
            return out("likely_ineligible", "eu_company_only", f["uis_can_apply"]["ev"])
        if norway.get("s") == "inferred" and norway.get("v") is None:
            return out("check", "eu_restricted", norway.get("ev"))
        if norway.get("s", "not_specified") == "not_specified":
            return out("check", "eu_country_unknown")
        rule = eu.role_rule(f["call_id"]["v"])
        if rule:
            e = eu_role_eligibility(f["call_id"]["v"], kind, career, full_record)
            if e:
                return out(e[0], e[1], rule[0])
            if kind in ("emeritus", "external", "adjunct"):
                return out("check", f"position_{kind}", (r.get("position") or {}).get("nb"))
            return out("no_restriction_found", "none_found")
    if f["uis_can_apply"]["v"] is False:
        return out("partner_only", "uis_not_applicant", f["uis_can_apply"]["ev"])
    # Career-stage rules. Numbers ("2–7 years since the doctorate") count only in
    # the project-manager requirements and stage words only in the call title:
    # FRIPRO texts mention their sister calls ("erfarne forskere, tidlig karriere"),
    # which must not trigger the other call's rule.
    pi = "\n".join(filter(None, [lang_text(f["pi_requirements"]["v"], lang) for lang in ("nb", "en")]))
    title = "\n".join(filter(None, [lang_text(f["title"]["v"], lang) for lang in ("nb", "en")]))

    def rule(numbers: str, words: str) -> str | None:
        if re.search(numbers, pi, re.I):
            return sentence_with(pi, numbers)
        if re.search(words, title, re.I):
            return sentence_with(title, words)
        return None

    # Upper limit on years since the doctorate (FRIPRO early career 2–7, mobility ≤ 7).
    ev = rule(r"mellom (to|2) og (syv|sju|7) år|maks(imalt)? (syv|sju|7) år|between (two|2) and (seven|7) years|"
              r"(at most|no more than|maximum( of)?) (seven|7) years",
              r"tidlig karriere|early[- ]career|unge forskertalent|young research talent")
    if ev:
        if kind in ("professor", "emeritus"):
            return out("likely_ineligible", "early_career_senior", ev)
        if career is not None and career > 12:
            return out("check", "early_career_long_record", ev)
    # Lower limit (FRIPRO experienced: at least six years since the doctorate).
    ev = rule(r"minst (seks|6) år|at least (six|6) years",
              r"erfarne forskere|experienced (researchers|scientists)|toppforsk|top researchers")
    if ev:
        if kind in ("phd", "postdoc"):
            return out("likely_ineligible", "senior_call_junior", ev)
        if full_record and career is not None and career < 6:
            return out("check", "senior_call_short_record", ev)
    # A submitted thesis is enough (FRIPRO mobility): PhD candidates should check.
    thesis = r"levert doktorgradsavhandling|levert avhandling|submitted (your|the|their) (doctoral )?thesis"
    if kind == "phd" and re.search(thesis, text, re.I):
        return out("check", "thesis_submitted", sentence_with(text, thesis))
    doctorate = r"doktorgrad|doctoral degree|ph\.?\s?d\.?[- ]degree|doctorate"
    if kind == "phd" and re.search(doctorate, text, re.I):
        return out("likely_ineligible", "doctorate_required", sentence_with(text, doctorate))
    if kind in ("emeritus", "external", "adjunct"):
        return out("check", f"position_{kind}", (r.get("position") or {}).get("nb"))
    return out("no_restriction_found", "none_found")


def suggested_role(category: str, elig: dict, kind: str | None) -> str:
    if elig["status"] == "partner_only":
        return "rd_partner"
    if elig["status"] == "likely_ineligible":
        return "team_member"
    if category == "high" and kind in ("professor", "faculty", None, "other"):
        return "pi_candidate"
    if kind in ("phd", "postdoc"):
        return "team_member"
    return "wp_contributor" if category in ("high", "medium") else "contributor"


# ---------------------------------------------------------------------- main
def recency_weights(years: np.ndarray, reference_year: int = config.REFERENCE_YEAR) -> np.ndarray:
    """1 for this year's (and in-press) papers, halving every recency_half_life_years."""
    return np.power(0.5, np.clip(reference_year - years, 0, None) / CFG["recency_half_life_years"])


def relevance(sims: np.ndarray) -> np.ndarray:
    """Cosine similarity -> 0–1 relevance on a fixed scale (config similarity)."""
    lo, hi = CFG["similarity"]
    return np.clip((sims - lo) / (hi - lo), 0, 1)


def title_terms(call: dict) -> list[str]:
    """Distinctive words of the call title, e.g. 'quantum'. The English title when there
    is one: papers are mostly in English, so a Norwegian word ('helse') rarely matches."""
    t = call["fields"]["title"]["v"]
    words = set()
    for w in re.findall(r"[a-zæøåA-ZÆØÅ][\w-]{3,}", t.get("en") or t.get("nb") or ""):
        w = w.lower()
        if w not in GENERIC and not w.isdigit():
            words.add(w)
    return sorted(words)


def term_hits(terms: list[str], papers: list[dict]) -> tuple[np.ndarray, list[list[str]], list[str]]:
    """Papers whose title or keywords contain a distinctive title word. Words found in
    more than keyword_max_share of all recent papers ("systems", "health") are too
    common to identify a topic and are dropped; the semantic score covers them."""
    texts = [" ".join([p.get("title") or ""] + (p.get("keywords") or [])) for p in papers]
    pats = [(t, re.compile(rf"\b{re.escape(t[:max(5, len(t) - 2)])}", re.I)) for t in terms]
    limit = CFG["keyword_max_share"] * len(papers)
    pats = [(t, pat) for t, pat in pats if sum(1 for x in texts if pat.search(x)) <= limit]
    hits, found = np.zeros(len(papers)), []
    for k, text in enumerate(texts):
        f = [t for t, pat in pats if pat.search(text)]
        found.append(f)
        hits[k] = 1.0 if f else 0.0
    return hits, found, [t for t, _ in pats]


NOT_EVIDENCE_TYPES = {"Editorial", "Erratum", "Note", "Letter", "Retracted"}
NOT_EVIDENCE_TITLE = re.compile(r"^\s*(corrigendum|correction|erratum|preface|editorial|retraction)", re.I)


def is_evidence(p: dict) -> bool:
    """Research output only: corrections, editorials and notes do not show expertise."""
    return p.get("type") not in NOT_EVIDENCE_TYPES and not NOT_EVIDENCE_TITLE.search(p.get("title") or "")


def main() -> None:
    calls = json.loads(config.CALLS.read_text(encoding="utf-8"))
    profiles_doc = json.loads(config.PROFILES.read_text(encoding="utf-8"))
    people = profiles_doc["researchers"]
    raw_papers = json.loads(config.RAW_ATLAS.read_text(encoding="utf-8"))["papers"]
    call_profiles = (json.loads(config.CALL_PROFILES.read_text(encoding="utf-8"))
                     if config.CALL_PROFILES.exists() else {})
    paper_ids, P = embed.load_papers()
    row = {e: k for k, e in enumerate(paper_ids)}
    years = np.array([int(raw_papers[e]["year"]) for e in paper_ids])
    recency = recency_weights(years)
    evidence_mask = np.array([1.0 if is_evidence(raw_papers[e]) else 0.0 for e in paper_ids])

    by_id = {r["scopus_id"]: r for r in people}
    rows_of = {r["scopus_id"]: [row[e] for e in r["paper_ids"] if e in row] for r in people}
    rows_of = {k: v for k, v in rows_of.items() if v}
    paper_sets = {k: set(by_id[k]["paper_ids"]) for k in rows_of}

    model = embed.load_model()
    out_calls = {}
    active = [c for c in calls["calls"] if c["fields"]["status"]["v"] != "closed"]
    # --changed-profiles (second pass in run_all.py, after profile_calls.py): reuse the
    # previous result of every call whose AI profile did not change.
    previous = {}
    if "--changed-profiles" in sys.argv and config.FUNDING_MATCHES.exists():
        prev = json.loads(config.FUNDING_MATCHES.read_text(encoding="utf-8"))
        same_inputs = (profiles_doc.get("generated"), calls.get("generated"),
                       json.loads(json.dumps(CFG)))  # as stored: tuples become lists in JSON
        if (prev.get("researchers_from"), prev.get("calls_from"), prev.get("settings")) == same_inputs:
            previous = prev["calls"]
    reused = 0
    for call in active:
        profile = call_profiles.get(call["id"])
        profile_key = profile["source_hash"] if profile else None
        if call["id"] in previous and previous[call["id"]].get("profile_key") == profile_key:
            out_calls[call["id"]] = previous[call["id"]]
            reused += 1
            continue
        if call["fields"].get("institution_level", {}).get("v"):
            # Applied for by the institution (MSCA COFUND, Researchers' Night): no researcher matches.
            out_calls[call["id"]] = {"aspects": [], "aspect_basis": "institution_level", "title_terms": [],
                                     "matches": [], "profile_key": profile_key}
            print(f"  {call['id']}: institution-level call – not matched to researchers")
            continue
        if call["fields"].get("open_field", {}).get("v"):
            # Open to all fields (e.g. FRIPRO): no topic to match on. Every researcher
            # is offered the call, with eligibility from its stated rules. Only the
            # exceptions are stored; everyone else is "no restriction found".
            elig, evidence = {}, {}
            for sid in rows_of:
                e = eligibility(call, by_id[sid])
                if e["status"] != "no_restriction_found":
                    elig[sid] = [e["status"], e["reason"]]
                    evidence.setdefault(e["reason"], e["evidence"])
            rule = eu.role_rule(call["fields"]["call_id"]["v"] or "") if call["source"] == "eu" else None
            out_calls[call["id"]] = {"aspects": [], "aspect_basis": "open_field", "title_terms": [], "matches": [],
                                     "open_eligibility": elig, "eligibility_evidence": evidence,
                                     "open_role": rule[2] if rule else None, "profile_key": profile_key}
            n_out = sum(1 for s, _ in elig.values() if s == "likely_ineligible")
            print(f"  {call['id']}: open to all fields – {len(rows_of) - n_out} researchers offered "
                  f"({n_out} probably not eligible, {len(elig) - n_out} to check)")
            continue
        scope, aspects = call_aspects(call, profile)
        queries = [scope] + [a["text"] for a in aspects]
        Q = embed.encode(model, queries, config.QUERY_PREFIX)
        R = relevance(P @ Q.T)                       # papers × (scope + aspects)
        scope_rel = R[:, 0]
        aspect_rel = R[:, 1:] if aspects else np.zeros((len(P), 0))
        lex, lex_found, terms = term_hits(title_terms(call), [raw_papers[e] for e in paper_ids])
        semantic = 0.5 * scope_rel + 0.5 * (aspect_rel.max(axis=1) if aspects else scope_rel)
        kw = CFG["keyword_weight"] if terms else 0.0
        paper_rel = (1 - kw) * semantic + kw * lex * (semantic > 0)  # words alone never make a match
        paper_rel = paper_rel * evidence_mask
        aspect_rel = aspect_rel * evidence_mask[:, None]
        weighted = paper_rel * recency
        aw = np.array([a["weight"] for a in aspects]) if aspects else np.zeros(0)

        scored, every = [], {}
        for sid, rows in rows_of.items():
            w = np.sort(weighted[rows])[::-1]
            s_scope = float(w[:3].sum() / 3)
            n_rel = float((recency[rows] * (paper_rel[rows] >= CFG["relevant_paper"])).sum())
            s_evidence = 1 - math.exp(-n_rel / 3)
            best_aspect = (aspect_rel[rows] * recency[rows, None]).max(axis=0) if aspects else np.zeros(0)
            covered = best_aspect >= CFG["relevant_paper"]
            s_cov = float((aw * covered).sum() / aw.sum()) if aspects else s_scope
            wts = CFG["weights"]
            score = wts["scope"] * s_scope + wts["coverage"] * s_cov + wts["evidence"] * s_evidence
            every[sid] = (score, sid, s_scope, s_cov, s_evidence, covered, best_aspect, rows)
            if score >= CFG["min_score"] and n_rel > 0:
                scored.append(every[sid])
        scored.sort(key=lambda x: -x[0])
        scored = scored[:CFG["max_matches_per_call"]]
        # Specialists: the researchers who best cover each aspect, listed even when their
        # overall fit is lower (e.g. a sensor expert for a call led by health services research).
        specialist_for = {}
        for j in range(len(aspects)):
            ranked = sorted((e for e in every.values() if e[5][j]), key=lambda e: -e[6][j])
            for e in ranked[:CFG["specialists_per_aspect"]]:
                specialist_for.setdefault(e[1], []).append(j)
        listed = {e[1] for e in scored}
        scored += sorted((every[sid] for sid in specialist_for if sid not in listed), key=lambda x: -x[0])

        matches = []
        for score, sid, s_scope, s_cov, s_ev, covered, best_aspect, rows in scored:
            r = by_id[sid]
            cat = ("high" if score >= CFG["categories"]["high"]
                   else "medium" if score >= CFG["categories"]["medium"] else "low")
            top = sorted(rows, key=lambda k: -weighted[k])[:3]
            elig = eligibility(call, r)
            matched, missing = [], []
            for j, a in enumerate(aspects):
                if covered[j]:
                    best = max(rows, key=lambda k: aspect_rel[k, j] * recency[k])
                    matched.append({"aspect": j, "paper": paper_ids[best], "rel": round(float(best_aspect[j]), 2)})
                else:
                    missing.append(j)
            matches.append({
                "id": sid, "score": round(score, 3), "category": cat,
                "components": {"scope": round(s_scope, 3), "coverage": round(s_cov, 3), "evidence": round(s_ev, 3)},
                "papers": [{"eid": paper_ids[k], "rel": round(float(paper_rel[k]), 2), "terms": lex_found[k]}
                           for k in top],
                "matched": matched, "missing": missing,
                "eligibility": elig, "role": suggested_role(cat, elig, position_kind(r)),
                "specialist_for": specialist_for.get(sid, []),
                "_covered": covered,
            })

        # Collaborators: complementary coverage, existing co-authorship, other departments.
        pool = {m["id"]: m for m in matches}
        cover_all = {}
        if aspects:
            for sid, rows in rows_of.items():
                cover_all[sid] = (aspect_rel[rows] * recency[rows, None]).max(axis=0) >= CFG["relevant_paper"]
        for m in matches:
            gaps = np.array([j in m["missing"] for j in range(len(aspects))])
            cands = []
            if gaps.any():
                for sid, cov in cover_all.items():
                    if sid == m["id"]:
                        continue
                    fills = gaps & cov
                    if not fills.any():
                        continue
                    gain = float((aw * fills).sum() / (aw * gaps).sum())
                    joint = len(paper_sets[m["id"]] & paper_sets[sid])
                    other_dept = by_id[sid]["department"] != by_id[m["id"]]["department"]
                    value = gain + (0.15 if joint else 0) + (0.05 if other_dept else 0) \
                        + (0.1 * pool[sid]["score"] if sid in pool else 0)
                    cands.append((value, sid, [int(j) for j in np.where(fills)[0]], joint, other_dept))
            cands.sort(key=lambda x: -x[0])
            m["collaborators"] = [{"id": sid, "fills": fills, "joint_papers": joint, "other_department": od}
                                  for _, sid, fills, joint, od in cands[:CFG["collaborators_per_match"]]]
            del m["_covered"]

        out_calls[call["id"]] = {
            "aspects": [{k: a[k] for k in ("label", "kind", "source", "evidence")} for a in aspects],
            "aspect_basis": "ai_profile" if profile else "call_text", "title_terms": terms,
            "matches": matches, "profile_key": profile_key,
        }
        n = sum(m["category"] != "low" for m in matches)
        print(f"  {call['id']}: {len(matches)} matches ({n} high/medium), {len(aspects)} aspects")
    if previous:
        print(f"Reused {reused} calls whose AI profile did not change.")

    config.FUNDING_MATCHES.write_text(json.dumps({
        "generated": datetime.now().isoformat(timespec="seconds"),
        "algorithm": CFG["algorithm"], "settings": CFG,
        "researchers_from": profiles_doc.get("generated"), "calls_from": calls.get("generated"),
        "papers_from_year": config.ACTIVE_FROM,
        "calls": out_calls}, ensure_ascii=False), encoding="utf-8")
    print(f"Matched {len(out_calls)} open/planned calls against {len(rows_of)} researchers.")


if __name__ == "__main__":
    main()
