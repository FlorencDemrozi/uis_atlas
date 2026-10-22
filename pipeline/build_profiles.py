#!/usr/bin/env python3
"""
Stage 2 – Build one profile per researcher.

Input:  config.RAW_ATLAS and config.RAW_DOCS (from collect_scopus.py),
        config/overrides.json
Output: config.PROFILES, config.MERGE_LOG, review CSVs in config.REVIEW_DIR
        (all licensed – local only, never commit)

Steps:
- Merge duplicate Scopus author IDs for the same person: forced merges from
  overrides, same ORCID, or same normalised name + department + a shared
  co-author. Name-only matches are not merged but listed for review.
- Keep researchers with at least config.MIN_RECENT_PUBLICATIONS papers in the
  last config.RECENT_YEARS years (overrides can force include/exclude).
- Compute per researcher: department, paper ids (newest first), counts,
  citations, publications per year, keywords, UiS co-authors, collaborating
  departments, first/last active year.

overrides.json format (keyed by any of the person's Scopus IDs):
  {"authors": {"123": {"name": "...", "department": "...",
                       "merge_with": ["456"], "include": true}}}
"""
import csv
import json
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from itertools import combinations

import config

NOT_STATED = config.NOT_STATED
SCOPUS_AUTHOR_URL = "https://www.scopus.com/authid/detail.uri?authorId={}"
TRANSLIT = str.maketrans({"ø": "o", "æ": "ae", "ð": "d", "þ": "th", "ß": "ss", "ł": "l", "đ": "d"})


# ---------------------------------------------------------------- names
def norm(text: str) -> str:
    text = (text or "").lower().translate(TRANSLIT)
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if c.isalnum())


def name_key(surname: str, given: str) -> str:
    """Surname plus first initial, accent- and punctuation-insensitive."""
    return f"{norm(surname)}|{norm(given)[:1]}"


def given_compatible(g1: str, g2: str) -> bool:
    """'Lennart' ~ 'L.', but 'Yu' !~ 'Yucong' and 'Emiel' !~ 'Emilius'."""
    t1 = [norm(t) for t in g1.replace(".", " ").replace("-", " ").split() if norm(t)]
    t2 = [norm(t) for t in g2.replace(".", " ").replace("-", " ").split() if norm(t)]
    if not t1 or not t2:
        return True
    if len(t1[0]) == 1 or len(t2[0]) == 1:
        return t1[0][0] == t2[0][0]
    return t1[0] == t2[0]


def split_name(full: str) -> tuple[str, str]:
    parts = (full or "").split()
    return (parts[-1], " ".join(parts[:-1])) if parts else ("", "")


# ---------------------------------------------------------------- merging
class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        self.parent[rb] = ra
        return True


def find_merges(authors: dict, papers: dict, name_parts: dict, overrides: dict):
    """Return (UnionFind, merge log, unmerged name-match candidates)."""
    uf, log, candidates = UnionFind(), [], []
    for auid in authors:
        uf.find(auid)

    def merge(ids: list[str], reason: str) -> None:
        if any(uf.union(ids[0], other) for other in ids[1:]):
            log.append({"ids": ids, "names": [authors[i]["name"] for i in ids], "reason": reason})

    for auid, ov in overrides.items():
        ids = [i for i in [auid, *ov.get("merge_with", [])] if i in authors]
        if len(ids) > 1:
            merge(ids, "override")

    by_orcid = defaultdict(list)
    for auid, a in authors.items():
        if a.get("orcid"):
            by_orcid[a["orcid"]].append(auid)
    for ids in by_orcid.values():
        if len(ids) > 1:
            merge(ids, "same ORCID")

    def coauthors(auid: str) -> set[str]:
        return {c for p in authors[auid]["papers"] for c in papers[p]["coauthor_ids"]} - {auid}

    by_name, given = defaultdict(list), {}
    for auid, a in authors.items():
        surname, given[auid] = name_parts.get(auid) or split_name(a["name"])
        by_name[name_key(surname, given[auid])].append(auid)
    for ids in by_name.values():
        for x, y in combinations(ids, 2):
            if uf.find(x) == uf.find(y):
                continue
            ax, ay = authors[x], authors[y]
            if set(ax["papers"]) & set(ay["papers"]):
                continue  # two different people on the same paper
            same_dept = ax["department"] == ay["department"]
            shared = coauthors(x) & coauthors(y)
            if same_dept and shared and given_compatible(given[x], given[y]):
                merge([x, y], f"same name, department and {len(shared)} shared co-author(s)")
            else:
                candidates.append({
                    "ids": [x, y], "names": [ax["name"], ay["name"]],
                    "departments": [ax["department"], ay["department"]],
                    "shared_coauthors": len(shared),
                })
    return uf, log, candidates


# ---------------------------------------------------------------- profiles
def year_of(paper: dict) -> int | None:
    y = paper.get("year") or ""
    return int(y) if y.isdigit() else None


def build(atlas: dict, name_parts: dict, overrides: dict, reference_year: int,
          recent_years: int, min_recent: int) -> dict:
    authors = {a["scopus_id"]: a for a in atlas["authors"]}
    papers = atlas["papers"]
    recent_from = reference_year - recent_years + 1

    uf, merge_log, candidates = find_merges(authors, papers, name_parts, overrides)
    clusters = defaultdict(list)
    for auid in authors:
        clusters[uf.find(auid)].append(auid)

    people, canon = {}, {}
    for members in clusters.values():
        members.sort(key=lambda i: -len(authors[i]["papers"]))
        main_id = members[0]
        ov = {}
        for i in members:
            ov.update(overrides.get(i, {}))
        dept_votes = Counter()
        for i in members:
            dept_votes[authors[i]["department"]] += len(authors[i]["papers"])
        real = [d for d, _ in dept_votes.most_common() if d != NOT_STATED]
        paper_ids = sorted({p for i in members for p in authors[i]["papers"]},
                           key=lambda p: (-(year_of(papers[p]) or 0), p))
        years = [y for p in paper_ids if (y := year_of(papers[p]))]
        people[main_id] = {
            "scopus_id": main_id,
            "scopus_ids": members,
            "name": ov.get("name") or authors[main_id]["name"],
            "orcid": next((authors[i]["orcid"] for i in members if authors[i].get("orcid")), None),
            "department": ov.get("department") or (real[0] if real else NOT_STATED),
            "paper_ids": paper_ids,
            "n_publications": len(paper_ids),
            "n_recent": sum(1 for y in years if y >= recent_from),
            "citations": sum(papers[p]["citations"] for p in paper_ids),
            "pubs_per_year": dict(sorted(Counter(str(y) for y in years).items())),
            "first_year": min(years, default=None),
            "last_year": max(years, default=None),
            "_include_override": ov.get("include"),
            "_affiliations": [s for i in members for s in authors[i].get("affiliation_strings", [])],
        }
        for i in members:
            canon[i] = main_id

    for pid, person in people.items():
        forced = person.pop("_include_override")
        person["included"] = forced if forced is not None else person["n_recent"] >= min_recent

    for pid, person in people.items():
        kw_count, kw_spellings = Counter(), defaultdict(Counter)
        co_count, dept_count = Counter(), Counter()
        for p in person["paper_ids"]:
            for k in papers[p]["keywords"]:
                kw_count[k.lower()] += 1
                kw_spellings[k.lower()][k] += 1
            co = {canon[c] for c in papers[p]["coauthor_ids"] if c in canon} - {pid}
            co_count.update(co)
            dept_count.update({people[c]["department"] for c in co} - {person["department"], NOT_STATED})
        person["keywords"] = [
            [max(kw_spellings[k].items(), key=lambda s: (s[1], sum(c.isupper() for c in s[0])))[0], n]
            for k, n in kw_count.most_common(30)]
        person["top_coauthors"] = [
            {"scopus_id": c, "name": people[c]["name"], "n_papers": n}
            for c, n in co_count.most_common() if people[c]["included"]][:10]
        person["collab_departments"] = dict(dept_count.most_common())

    return {"people": people, "merge_log": merge_log, "candidates": candidates,
            "recent_from": recent_from}


def threshold_table(years_by_person: dict, reference_year: int) -> list[str]:
    """How many researchers alternative inclusion rules would give (for tuning)."""
    rows = ["  papers ≥   last 1 yr   last 2 yrs   last 3 yrs"]
    for n in (1, 2, 3, 4, 5):
        counts = []
        for yrs in (1, 2, 3):
            start = reference_year - yrs + 1
            counts.append(sum(1 for years in years_by_person.values()
                              if sum(1 for y in years if y >= start) >= n))
        rows.append(f"  {n:>8}   {counts[0]:>9}   {counts[1]:>10}   {counts[2]:>10}")
    return rows


# ---------------------------------------------------------------- I/O
def load_raw_docs() -> tuple[dict, Counter, Counter]:
    """Surname/given name per author, plus total and per-year paper counts per UiS author."""
    name_parts, seen = {}, set()
    years_by_author = defaultdict(list)
    with config.RAW_DOCS.open(encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            if e.get("eid") in seen:
                continue
            seen.add(e.get("eid"))
            y = (e.get("prism:coverDate") or "")[:4]
            authors = e.get("author") or []
            for a in authors if isinstance(authors, list) else [authors]:
                auid = a.get("authid")
                if not auid:
                    continue
                name_parts.setdefault(auid, (a.get("surname") or "", a.get("given-name") or ""))
                if y.isdigit():
                    years_by_author[auid].append(int(y))
    return name_parts, years_by_author


def write_csv(path, header: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:  # utf-8-sig: opens cleanly in Excel
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main() -> None:
    atlas = json.loads(config.RAW_ATLAS.read_text(encoding="utf-8"))
    overrides = json.loads(config.OVERRIDES.read_text(encoding="utf-8")).get("authors", {})
    name_parts, years_by_author = load_raw_docs()

    res = build(atlas, name_parts, overrides, config.REFERENCE_YEAR,
                config.RECENT_YEARS, config.MIN_RECENT_PUBLICATIONS)
    people = res["people"]
    included = [p for p in people.values() if p["included"]]
    included.sort(key=lambda p: (p["department"], p["name"]))

    config.INTERIM.mkdir(parents=True, exist_ok=True)
    out = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "reference_year": config.REFERENCE_YEAR,
        "recent_from": res["recent_from"],
        "min_recent_publications": config.MIN_RECENT_PUBLICATIONS,
        "researchers": [{k: v for k, v in p.items() if not k.startswith("_") and k != "included"}
                        for p in included],
    }
    config.PROFILES.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    config.MERGE_LOG.write_text(json.dumps(res["merge_log"], ensure_ascii=False, indent=1),
                                encoding="utf-8")

    # ---- review files for the project owner
    write_csv(config.REVIEW_DIR / "researchers.csv",
              ["status", "scopus_id", "other_scopus_ids", "name", "department", "n_publications",
               f"n_since_{res['recent_from']}", "last_year", "affiliation_example", "scopus_url"],
              [["included" if p["included"] else "dropped", p["scopus_id"],
                " ".join(p["scopus_ids"][1:]), p["name"], p["department"], p["n_publications"],
                p["n_recent"], p["last_year"], (p["_affiliations"] or [""])[0],
                SCOPUS_AUTHOR_URL.format(p["scopus_id"])]
               for p in sorted(people.values(),
                               key=lambda p: (not p["included"], p["department"], p["name"]))])
    unmatched = sorted(atlas["unmatched_authors"],
                       key=lambda u: -sum(1 for y in years_by_author.get(u["scopus_id"], [])
                                          if y >= res["recent_from"]))
    write_csv(config.REVIEW_DIR / "unmatched_uis_authors.csv",
              ["scopus_id", "name", "n_papers_total", f"n_since_{res['recent_from']}",
               "affiliation_strings", "scopus_url"],
              [[u["scopus_id"], u["name"], len(years_by_author.get(u["scopus_id"], [])),
                sum(1 for y in years_by_author.get(u["scopus_id"], []) if y >= res["recent_from"]),
                " || ".join(u["affiliation_strings"]), SCOPUS_AUTHOR_URL.format(u["scopus_id"])]
               for u in unmatched])
    write_csv(config.REVIEW_DIR / "possible_duplicates.csv",
              ["scopus_id_1", "name_1", "department_1", "scopus_id_2", "name_2", "department_2",
               "shared_coauthors"],
              [[c["ids"][0], c["names"][0], c["departments"][0],
                c["ids"][1], c["names"][1], c["departments"][1], c["shared_coauthors"]]
               for c in res["candidates"]])

    # ---- report
    years_by_person = {pid: [y for p in person["paper_ids"] if (y := year_of(atlas["papers"][p]))]
                    for pid, person in people.items()}
    print(f"{len(atlas['authors'])} Scopus author IDs → {len(people)} people after "
          f"{len(res['merge_log'])} merges ({len(res['candidates'])} possible duplicates left for review).")
    print(f"Included: {len(included)} with ≥{config.MIN_RECENT_PUBLICATIONS} papers since "
          f"{res['recent_from']}; dropped {len(people) - len(included)}.\n")
    for dept, n in Counter(p["department"] for p in included).most_common():
        print(f"  {n:4d}  {dept}")
    print("\nResearchers under other inclusion rules (for tuning config.py):")
    print("\n".join(threshold_table(years_by_person, config.REFERENCE_YEAR)))
    print(f"\nWrote {config.PROFILES.name}, {config.MERGE_LOG.name} and review CSVs in "
          f"{config.REVIEW_DIR} (local only, never commit).")


if __name__ == "__main__":
    main()
