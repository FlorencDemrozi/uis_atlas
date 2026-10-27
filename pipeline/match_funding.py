#!/usr/bin/env python3
"""
Stage 4c – Match UiS researchers to open and planned funding calls, and suggest
internal collaborators who complement them.

Input:  config.CALLS, config.CALL_PROFILES (optional), config.PROFILES,
        paper vectors from embed.py, papers in config.RAW_ATLAS
Output: config.FUNDING_MATCHES

Method (settings in config.FUNDING_MATCH; transparent and reproducible):
1. Each call is split into "aspects": the competencies, methods and domains of
   its AI profile when one exists, otherwise the thematic bullets and
   paragraphs of the official call text. A "scope" text (title, summary,
   themes) describes the call as a whole.
2. Every recent paper (last config.ACTIVE_YEARS years) is compared with the
   scope and each aspect (same embedding model as the search, "query:" prefix
   for the call). Similarities are turned into a relevance of 0–1 relative to
   all UiS papers for that call, and weighted by recency (half-life
   recency_half_life_years).
3. Score = weights.scope × scope alignment (mean of the 3 most relevant papers)
         + weights.coverage × share of the call's aspects covered by a paper
         + weights.evidence × amount of relevant work (saturating with count)
   Category: High / Medium / Low by config thresholds. A ranking aid for one
   call – not a probability of funding.
4. Eligibility is checked separately, only from conditions stated in the call
   text, and shown with the sentence it rests on. It never raises a score.
5. Collaborators: other UiS researchers whose papers cover aspects the matched
   researcher does not, preferring existing co-authors (verified by shared
   papers) and other departments. All are suggestions, not commitments.
"""
import json
import math
import re
from datetime import datetime

import numpy as np

import config
import embed

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


def call_aspects(call: dict, profile: dict | None) -> tuple[str, list[dict]]:
    f = call["fields"]
    title = lang_text(f["title"]["v"])
    themes = lang_text(f["themes"]["v"]) or []
    scope = ". ".join(filter(None, [title, lang_text(f["summary"]["v"]), ", ".join(themes)]))
    aspects = []
    if profile:
        p = profile["profile"]
        for c in p["competencies"]:
            aspects.append({"label": c["name"], "text": f"{c['name']}: {c['rationale']}", "kind": c["kind"],
                            "source": "ai", "evidence": c.get("evidence") or ""})
        for key in ("methods", "application_domains"):
            for x in p[key]:
                aspects.append({"label": x, "text": x, "kind": "complementary", "source": "ai", "evidence": ""})
    else:
        passage = lang_text(f["research_scope"]["v"]) or lang_text(f["description"]["v"]) or ""
        seen = set()
        for line in passage.split("\n"):
            text = line.lstrip("• ").strip()
            words = text.split()
            if not 5 <= len(words) <= 120 or NOISE.search(text) or text.lower() in seen:
                continue
            seen.add(text.lower())
            label = " ".join(words[:14]) + ("…" if len(words) > 14 else "")
            aspects.append({"label": label, "text": text, "kind": "scope", "source": "call_text",
                            "evidence": text if len(words) <= 60 else ""})
    weights = {"core": 1.0, "scope": 1.0, "complementary": 0.6, "mandatory_partner": 0.3, "optional": 0.3}
    for a in aspects:
        a["weight"] = weights[a["kind"]]
    aspects.sort(key=lambda a: -a["weight"])
    return scope, aspects[:CFG["max_aspects"]]


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


def eligibility(call: dict, r: dict) -> dict:
    """{"status", "reason", "evidence"} from conditions stated in the call text."""
    f = call["fields"]
    text = "\n".join(filter(None, [lang_text(f["title"]["v"], "nb"), lang_text(f["title"]["v"], "en")]
                         + [lang_text(f[k]["v"], lang) for k in ("pi_requirements", "eligible_applicants",
                                                                  "description", "summary")
                            for lang in ("nb", "en")]))
    kind = position_kind(r)
    out = lambda status, reason, ev=None: {"status": status, "reason": reason, "evidence": ev}
    if f["uis_can_apply"]["v"] is False:
        return out("partner_only", "uis_not_applicant", f["uis_can_apply"]["ev"])
    early = r"tidlig karriere|early[- ]career|unge forskertalent|young research talent"
    if re.search(early, text, re.I):
        ev = sentence_with(text, early)
        if kind in ("professor", "emeritus"):
            return out("likely_ineligible", "early_career_senior", ev)
        if r.get("first_year") and r["first_year"] < config.REFERENCE_YEAR - 12:
            return out("check", "early_career_long_record", ev)
    senior = r"erfarne forskere|experienced researchers|toppforsk"
    if re.search(senior, text, re.I) and kind in ("phd", "postdoc"):
        return out("likely_ineligible", "senior_call_junior", sentence_with(text, senior))
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
    """Distinctive words of the call title (both languages), e.g. 'quantum'."""
    words = set()
    for t in (call["fields"]["title"]["v"].get("nb"), call["fields"]["title"]["v"].get("en")):
        for w in re.findall(r"[a-zæøåA-ZÆØÅ][\w-]{3,}", t or ""):
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
    for call in active:
        profile = call_profiles.get(call["id"])
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

        scored = []
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
            if score >= CFG["min_score"] and n_rel > 0:
                scored.append((score, sid, s_scope, s_cov, s_evidence, covered, best_aspect, rows))
        scored.sort(key=lambda x: -x[0])
        scored = scored[:CFG["max_matches_per_call"]]

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
            "matches": matches,
        }
        n = sum(m["category"] != "low" for m in matches)
        print(f"  {call['id']}: {len(matches)} matches ({n} high/medium), {len(aspects)} aspects")

    config.FUNDING_MATCHES.write_text(json.dumps({
        "generated": datetime.now().isoformat(timespec="seconds"),
        "algorithm": CFG["algorithm"], "settings": CFG,
        "researchers_from": profiles_doc.get("generated"), "papers_from_year": config.ACTIVE_FROM,
        "calls": out_calls}, ensure_ascii=False), encoding="utf-8")
    print(f"Matched {len(out_calls)} open/planned calls against {len(rows_of)} researchers.")


if __name__ == "__main__":
    main()
