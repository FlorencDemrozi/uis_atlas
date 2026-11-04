#!/usr/bin/env python3
"""
Stage 2b – External partner institutions of each researcher, from the Scopus records
already collected (no new API requests).

Input:  config.PROFILES (build_profiles.py), config.RAW_DOCS and config.RAW_AUTHOR_DOCS
Output: config.PARTNERS (local; export_public.py publishes the allowed part)

For every paper of an included researcher, the institutions of the *other* authors
are counted, except UiS itself: "partner institution X, N papers" means N of the
researcher's papers have at least one co-author at X. Only institutions are kept
(Scopus affiliation id, name, city, country), never the external people
(docs/DATA_POLICY.md §2). Papers with more than config.PARTNER_MAX_AUTHORS authors
(large consortia) are left out, so one such paper does not add hundreds of
institutions.
"""
import json
from collections import Counter, defaultdict

import config
from collect_scopus import as_list, is_uis


def read_entries() -> dict[str, dict]:
    """Raw Scopus search records by EID (UiS papers and papers at other affiliations)."""
    entries = {}
    for path in (config.RAW_DOCS, config.RAW_AUTHOR_DOCS):
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as f:
            for line in f:
                e = json.loads(line)
                if e.get("eid"):
                    entries[e["eid"]] = e
    return entries


def author_count(entry: dict) -> int:
    n = entry.get("author-count")
    n = n.get("$") if isinstance(n, dict) else n
    try:
        return int(n or 0) or len(as_list(entry.get("author")))
    except ValueError:
        return len(as_list(entry.get("author")))


def partners_of_paper(entry: dict, own_ids: set[str]) -> set[str] | None:
    """Affiliation ids of the co-authors (not the researcher, not UiS); None when the
    researcher is not on the author list (cannot tell their own affiliation apart)."""
    authors = as_list(entry.get("author"))
    if not any(a.get("authid") in own_ids for a in authors):
        return None
    uis = {a.get("afid") for a in as_list(entry.get("affiliation")) if is_uis(a.get("afid"), a.get("affilname"))}
    uis.add(config.AFID)
    out = set()
    for a in authors:
        if a.get("authid") in own_ids:
            continue
        out.update(x.get("$") for x in as_list(a.get("afid")) if x.get("$"))
    return out - uis


def build(profiles: list[dict], entries: dict[str, dict], max_authors: int) -> dict:
    names = defaultdict(Counter)   # afid -> (name, city, country) spellings
    for e in entries.values():
        for a in as_list(e.get("affiliation")):
            if a.get("afid") and a.get("affilname"):
                names[a["afid"]][(a["affilname"], a.get("affiliation-city") or None,
                                  a.get("affiliation-country") or None)] += 1
    per_researcher = {}
    skipped = 0
    for r in profiles:   # profiles.json holds the included researchers only
        own = set(r["scopus_ids"])
        count, by_country = Counter(), Counter()
        for eid in r["paper_ids"]:
            e = entries.get(eid)
            if not e:
                continue   # NVA-only output: no affiliation data
            if author_count(e) > max_authors:
                skipped += 1
                continue
            found = partners_of_paper(e, own)
            found = {a for a in found or () if a in names}
            count.update(found)
            # Papers per country: a paper with two partners in one country counts once.
            by_country.update({place(names, a)[2] for a in found} - {None})
        if count:
            per_researcher[r["scopus_id"]] = {"institutions": dict(count.most_common()),
                                              "countries": dict(by_country.most_common())}
    used = {a for c in per_researcher.values() for a in c["institutions"]}
    institutions = {}
    for afid in sorted(used):
        name, city, country = place(names, afid)
        institutions[afid] = {"name": name, "city": city, "country": country}
    return {"institutions": institutions, "researchers": per_researcher, "skipped_large": skipped}


def place(names: dict, afid: str) -> tuple:
    """(name, city, country) of an institution: its most frequent spelling."""
    return names[afid].most_common(1)[0][0]


def main() -> None:
    profiles = json.loads(config.PROFILES.read_text(encoding="utf-8"))["researchers"]
    entries = read_entries()
    out = build(profiles, entries, config.PARTNER_MAX_AUTHORS)
    config.PARTNERS.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    countries = {i["country"] for i in out["institutions"].values() if i["country"]}
    print(f"Partner institutions: {len(out['institutions'])} in {len(countries)} countries for "
          f"{len(out['researchers'])} researchers ({out['skipped_large']} paper credits with more than "
          f"{config.PARTNER_MAX_AUTHORS} authors left out). Output: {config.PARTNERS}")


if __name__ == "__main__":
    main()
