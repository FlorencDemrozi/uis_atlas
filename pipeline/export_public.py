#!/usr/bin/env python3
"""
Stage 5 – Export the public dataset for the website. THE LICENCE GATE.

Input:  profiles, summaries, embeddings (data/interim/), config/exclusions.json,
        config/overrides.json, papers in config.RAW_ATLAS
Output: data/public/  (researchers.json, papers.json, stats.json, meta.json,
        vectors.bin once embeddings exist)

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

RESEARCHER_FIELDS = [
    "scopus_id", "name", "orcid", "faculty", "department", "position", "summary", "tags",
    "n_publications", "n_uis", "citations", "pubs_per_year", "first_year", "last_year",
    "top_coauthors", "collab_departments", "paper_ids", "other_paper_ids", "scopus_metrics", "links",
]
SCOPUS_METRICS = ["documents", "citations", "h_index"]   # as shown on the Scopus author page

PAPER_FIELDS = [
    "eid", "title", "year", "venue", "type", "doi", "citations",
    "keywords", "uis_author_ids",
]

MIN_COPIED_WORDS = 8   # a public sentence this long that also occurs in an abstract fails


def allow(record: dict, fields: list[str]) -> dict:
    return {k: record.get(k) for k in fields}


def links_for(r: dict, extra: dict) -> dict:
    links = {"scopus": f"https://www.scopus.com/authid/detail.uri?authorId={r['scopus_id']}"}
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
    unit, where key is "department" or "faculty"."""
    unit_of = {r["scopus_id"]: r[key] for r in researchers}
    per_unit = defaultdict(lambda: {"researchers": 0, "papers": set(), "citations": 0})
    for r in researchers:
        u = per_unit[r[key]]
        u["researchers"] += 1
        u["papers"].update(r["paper_ids"])
    years, themes = defaultdict(Counter), defaultdict(Counter)
    collab = Counter()
    for eid, p in papers.items():
        units = {unit_of[a] for a in p["uis_author_ids"]}
        for u in units:
            years[u][p["year"]] += 1
            per_unit[u]["citations"] += p["citations"] or 0
            themes[u].update({k.lower() for k in p["keywords"]})
        for a, b in combinations(sorted(units), 2):
            collab[(a, b)] += 1
    return {
        "units": {u: {"researchers": v["researchers"], "papers": len(v["papers"]),
                      "citations": v["citations"]} for u, v in sorted(per_unit.items())},
        "papers_per_year": {u: dict(sorted(c.items())) for u, c in sorted(years.items())},
        "collaboration": [{"a": a, "b": b, "papers": n} for (a, b), n in collab.most_common()],
        "top_themes": {u: c.most_common(20) for u, c in sorted(themes.items())},
    }


def build_stats(researchers: list[dict], papers: dict) -> dict:
    return {"departments": unit_stats(researchers, papers, "department"),
            "faculties": unit_stats(researchers, papers, "faculty")}


def main() -> None:
    profiles = json.loads(config.PROFILES.read_text(encoding="utf-8"))
    atlas = json.loads(config.RAW_ATLAS.read_text(encoding="utf-8"))
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
        s = summaries.get(r["scopus_id"], {})
        metrics = r.get("scopus_metrics")
        rec = dict(r, summary=ov.get("summary") or s.get("summary"), tags=s.get("tags") or [],
                   links=links_for(r, ov.get("links")),
                   scopus_metrics=allow(metrics, SCOPUS_METRICS) if metrics else None,
                   top_coauthors=[c for c in r["top_coauthors"] if c["scopus_id"] in included])
        researchers.append(allow(rec, RESEARCHER_FIELDS))

    used = {p for r in researchers for p in r["paper_ids"]}
    papers = {}
    for eid in sorted(used):
        p = atlas["papers"][eid]
        uis = sorted({canon[a] for a in p["coauthor_ids"] if a in canon})
        papers[eid] = allow(dict(p, eid=eid, uis_author_ids=uis), PAPER_FIELDS)

    check_no_copied_text(researchers, [atlas["papers"][e].get("abstract") for e in used])

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
    }

    config.PUBLIC.mkdir(parents=True, exist_ok=True)
    out = {"researchers.json": researchers, "papers.json": papers,
           "stats.json": build_stats(researchers, papers), "meta.json": meta}
    for name, data in out.items():
        (config.PUBLIC / name).write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                                          encoding="utf-8")
    if not config.EMBEDDINGS_DIR.exists():
        print("No embeddings yet (stage 4) – vectors.bin not written; the site uses keyword search only.")
    print(f"Exported {len(researchers)} researchers ({len(excluded)} exclusions) and "
          f"{len(papers)} papers to {config.PUBLIC}")


if __name__ == "__main__":
    main()
