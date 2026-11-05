#!/usr/bin/env python3
"""
Stage 5 – Export the public dataset for the website. THE LICENCE GATE.

Input:  profiles, summaries, embeddings (data/interim/), config/exclusions.json,
        config/overrides.json, papers in config.PAPERS (build_profiles.py)
Output: data/public/  (researchers.json, papers.json, stats.json, meta.json,
        partners.json once build_partners.py has run, vectors.bin once embeddings exist)

Only fields in the allow-lists below may be written. Everything else is dropped.
Never add abstracts or raw affiliation strings (docs/DATA_POLICY.md §2).

Summaries and embeddings are optional until stages 3–4 exist; researchers are
then exported without them.
"""
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from itertools import combinations

import config
from fsutil import write_text

RESEARCHER_FIELDS = [
    "scopus_id", "name", "orcid", "email", "faculty", "department", "position", "summary", "tags",
    "n_publications", "n_uis", "output_types", "citations", "pubs_per_year", "first_year", "last_year",
    "top_coauthors", "collab_departments", "other_paper_ids", "scopus_metrics", "links",
]
# Not in researchers.json (to keep it small): paper_ids. Each paper lists its authors
# (uis_author_ids), and the site rebuilds every researcher's paper list from that,
# newest first (web/src/data.ts), as build_profiles.py orders it.
SCOPUS_METRICS = ["documents", "citations", "h_index"]   # as shown on the Scopus author page

PAPER_FIELDS = [
    "title", "year", "venue", "type", "doi", "citations",
    "keywords", "uis_author_ids", "category",
]
# papers.json is keyed by paper id ("nva-..." for NVA-only outputs, whose link the
# site builds from the id). Empty fields are left out to keep the file small; the
# site fills them in (web/src/data.ts). "category" is left out where the site can
# derive it: from "type" via meta.json "category_of", else "article".

MIN_COPIED_WORDS = 8   # a public sentence this long that also occurs in an abstract fails


def allow(record: dict, fields: list[str]) -> dict:
    return {k: record.get(k) for k in fields}


def compact(record: dict) -> dict:
    return {k: v for k, v in record.items() if v not in (None, [], "")}


def default_category(paper: dict) -> str:
    """The category the site assumes when papers.json has none (web/src/data.ts)."""
    return config.category_of(paper["type"]) if paper.get("type") else "article"


def links_for(r: dict, extra: dict) -> dict:
    links = {}
    if not r["scopus_id"].startswith("nva-"):   # NVA-only people have no Scopus profile
        links["scopus"] = f"https://www.scopus.com/authid/detail.uri?authorId={r['scopus_id']}"
    if r.get("cristin_id"):
        links["nva"] = config.NVA_PERSON_URL.format(r["cristin_id"])
    if r.get("orcid"):
        links["orcid"] = f"https://orcid.org/{r['orcid']}"
    uis = r.get("uis_links") or {}
    if uis.get("nb"):
        links["uis"] = uis["nb"]
    if uis.get("en"):
        links["uis_en"] = uis["en"]
    links.update(extra or {})
    return links


def sentences(text: str) -> list[str]:
    return [s.strip().lower() for s in re.split(r"(?<=[.!?])\s+", text or "")
            if len(s.split()) >= MIN_COPIED_WORDS]


def check_no_copied_text(researchers: list[dict], abstracts: list[str]) -> None:
    corpus = " ".join(a.lower() for a in abstracts if a)
    for r in researchers:
        for s in sentences(r.get("summary") or ""):
            if s in corpus:
                raise SystemExit(f"Licence check failed: summary of {r['name']} copies an abstract "
                                 f"sentence. Regenerate it or override it in config/overrides.json.")


def unit_stats(researchers: list[dict], papers: dict, key: str) -> dict:
    """Researchers, papers, citations, papers per year, collaboration and themes per
    unit, where key is "department" or "faculty". Publications only (no lectures,
    media, artistic work: see config.PUBLICATION_CATEGORIES)."""
    unit_of = {r["scopus_id"]: r[key] for r in researchers}
    per_unit = defaultdict(lambda: {"researchers": 0, "papers": set(), "citations": 0})
    for r in researchers:
        u = per_unit[r[key]]
        u["researchers"] += 1
        u["papers"].update(p for p in r["paper_ids"] if config.is_publication(papers[p]))
    years, themes = defaultdict(Counter), defaultdict(Counter)
    collab = Counter()
    for eid, p in papers.items():
        if not config.is_publication(p):
            continue
        units = {unit_of[a] for a in p.get("uis_author_ids", [])}
        for u in units:
            years[u][p["year"]] += 1
            per_unit[u]["citations"] += p.get("citations") or 0
            themes[u].update(sorted({k.lower() for k in p.get("keywords", [])}))   # sorted: stable ties
        for a, b in combinations(sorted(units), 2):
            collab[(a, b)] += 1
    return {
        "units": {u: {"researchers": v["researchers"], "papers": len(v["papers"]),
                      "citations": v["citations"]} for u, v in sorted(per_unit.items())},
        "papers_per_year": {u: dict(sorted(c.items())) for u, c in sorted(years.items())},
        "collaboration": [{"a": a, "b": b, "papers": n} for (a, b), n in collab.most_common()],
        "top_themes": {u: c.most_common(20) for u, c in sorted(themes.items())},
    }


def export_partners(partners: dict, included: set[str]) -> dict:
    """partners.json for the site: per researcher on the site, partner institutions and
    countries with the number of shared papers, most first. Institutions: Scopus
    affiliation id -> [name, city, country] only (no people, no raw affiliation strings)."""
    researchers = {}
    for sid, p in sorted(partners["researchers"].items()):
        if sid in included:
            researchers[sid] = {"i": [[a, n] for a, n in p["institutions"].items()],
                                "c": [[c, n] for c, n in p["countries"].items()]}
    used = {a for r in researchers.values() for a, _ in r["i"]}
    institutions = {a: [i["name"], i["city"], i["country"]]
                    for a, i in sorted(partners["institutions"].items()) if a in used}
    return {"institutions": institutions, "researchers": researchers}


def build_stats(researchers: list[dict], papers: dict) -> dict:
    return {"departments": unit_stats(researchers, papers, "department"),
            "faculties": unit_stats(researchers, papers, "faculty")}


def main() -> None:
    profiles = json.loads(config.PROFILES.read_text(encoding="utf-8"))
    all_papers = json.loads(config.PAPERS.read_text(encoding="utf-8"))
    excluded = set(json.loads(config.EXCLUSIONS.read_text(encoding="utf-8")).get("scopus_ids", []))
    overrides = json.loads(config.OVERRIDES.read_text(encoding="utf-8")).get("authors", {})
    summaries = (json.loads(config.SUMMARIES.read_text(encoding="utf-8"))
                 if config.SUMMARIES.exists() else {})

    people = [r for r in profiles["researchers"] if not excluded & set(r["scopus_ids"])]
    canon = {i: r["scopus_id"] for r in people for i in r["scopus_ids"]}
    included = {r["scopus_id"] for r in people}

    researchers = []
    for r in people:
        ov = {}
        for i in r["scopus_ids"]:
            ov.update(overrides.get(i, {}))
        # A summary only while the researcher has recent papers (the summary cache may still
        # hold one for someone whose papers all aged out).
        active = any(config.is_active_paper(all_papers[e]) for e in r["paper_ids"] if e in all_papers)
        s = summaries.get(r["scopus_id"], {}) if active else {}
        metrics = r.get("scopus_metrics")
        rec = dict(r, summary=ov.get("summary") or s.get("summary"), tags=s.get("tags") or [],
                   links=links_for(r, ov.get("links")),
                   scopus_metrics=allow(metrics, SCOPUS_METRICS) if metrics else None,
                   top_coauthors=[c for c in r["top_coauthors"] if c["scopus_id"] in included])
        researchers.append(allow(rec, RESEARCHER_FIELDS))

    # Authors per paper from the researchers' own paper lists, so the two can never
    # disagree (the site rebuilds the paper lists from these).
    authors_of = defaultdict(list)
    for r in people:
        for eid in r["paper_ids"]:
            authors_of[eid].append(r["scopus_id"])
    used = set(authors_of)
    papers = {}
    for eid in sorted(used):
        p = all_papers[eid]
        rec = allow(dict(p, uis_author_ids=sorted(authors_of[eid])), PAPER_FIELDS)
        if eid.startswith("nva-"):
            rec.pop("type")   # NVA's own type names: the site shows the category
        if rec.get("category") == default_category(rec):
            rec.pop("category")
        papers[eid] = compact(rec)

    check_no_copied_text(researchers, [all_papers[e].get("abstract") for e in used])
    # Statistics need what the slim files leave out: paper lists and every category.
    stats = build_stats(
        [dict(rec, paper_ids=r["paper_ids"]) for rec, r in zip(researchers, people)],
        {e: dict(p, category=all_papers[e].get("category", "article")) for e, p in papers.items()})

    meta = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "institution": config.INSTITUTION_NAME,
        "faculties": [{"name": f["name"], "departments": [d["name"] for d in f["departments"]]}
                      for f in config.FACULTIES],
        "period": {"first_year": config.FIRST_YEAR, "recent_from": profiles["recent_from"]},
        "inclusion": {"confirmed": {"min": profiles["min_recent_publications"],
                                    "from": profiles["recent_from"]},
                      "unconfirmed": {"min": profiles["unconfirmed_min_recent_publications"],
                                      "from": profiles["unconfirmed_from"]}},
        "n_researchers": len(researchers),
        "n_papers": len(papers),
        "embedding_model": config.EMBED_MODEL,
        "summary_model": config.SUMMARY_MODEL if summaries else None,
        "has_summaries": bool(summaries),
        "has_vectors": False,
        "has_partners": config.PARTNERS.exists(),
        # Scopus document type -> output category, for papers without "category".
        "category_of": {t: config.category_of(t) for t in sorted({p["type"] for p in papers.values() if p.get("type")})},
    }

    config.PUBLIC.mkdir(parents=True, exist_ok=True)
    out = {"researchers.json": researchers, "papers.json": papers,
           "stats.json": stats, "meta.json": meta}
    if config.PARTNERS.exists():   # build_partners.py (stage 2b)
        out["partners.json"] = export_partners(json.loads(config.PARTNERS.read_text(encoding="utf-8")),
                                               {r["scopus_id"] for r in researchers})
    for name, data in out.items():
        write_text(config.PUBLIC / name, json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    if not config.EMBEDDINGS_DIR.exists():
        print("No embeddings yet (stage 4) – vectors.bin not written; the site uses keyword search only.")
    print(f"Exported {len(researchers)} researchers ({len(excluded)} exclusions) and "
          f"{len(papers)} papers to {config.PUBLIC}")


if __name__ == "__main__":
    main()
