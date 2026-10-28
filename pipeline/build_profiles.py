#!/usr/bin/env python3
"""
Stage 2 – Build one profile per researcher.

Input:  config.RAW_ATLAS and config.RAW_DOCS (from collect_scopus.py),
        config.DIRECTORY (from collect_directory.py, optional),
        config/overrides.json
Output: config.PROFILES, config.MERGE_LOG, review CSVs in config.REVIEW_DIR
        (all licensed or personal data – local only, never commit)

Steps:
- Match each Scopus author to the UiS employee directory by name (see
  pipeline/directory.py). A match confirms the person as current staff and
  gives today's department, position and UiS profile link. Staff listed only in
  excluded units (national centres, museum, divisions) are left out.
- Merge duplicate Scopus author IDs for the same person: forced merges from
  overrides, same ORCID, the same directory person, or same normalised name +
  department + a shared co-author. Name-only matches are not merged but listed
  for review.
- Department: override, else directory, else Scopus affiliations.
- Keep researchers with enough recent papers: confirmed staff need
  config.MIN_RECENT_PUBLICATIONS in config.RECENT_YEARS years (0: all current
  staff with a Scopus profile), others the stricter config.UNCONFIRMED_* rule
  (overrides can force include/exclude).
- Compute per researcher: faculty, department, position, paper ids (newest
  first), counts, citations, publications per year, keywords, UiS co-authors,
  collaborating departments, first/last active year.

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
from directory import Directory

NOT_STATED_KEYS = config.NOT_STATED_KEYS
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


def find_merges(authors: dict, papers: dict, name_parts: dict, overrides: dict,
                dir_match: dict | None = None):
    """Return (UnionFind, merge log, unmerged name-match candidates)."""
    uf, log, candidates = UnionFind(), [], []
    dir_match = dir_match or {}
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

    # Several Scopus IDs with a good name match to the same current employee.
    by_employee = defaultdict(list)
    for auid, (entry, score) in dir_match.items():
        if score >= 2:
            by_employee[entry["id"]].append(auid)
    for ids in by_employee.values():
        for x, y in combinations(ids, 2):
            if not set(authors[x]["papers"]) & set(authors[y]["papers"]):
                merge([x, y], "same person in the UiS employee directory")

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
            elif any(a["department"] or a["scopus_id"] in dir_match for a in (ax, ay)):
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


def place(scopus_dept: str | None, entry: dict | None) -> tuple[str | None, str]:
    """(department, source) from the directory entry and the Scopus department."""
    if entry is None:
        return scopus_dept, "scopus"
    if entry["excluded"]:
        return None, "directory: unit not in the atlas"
    if entry["departments"]:
        dept = scopus_dept if scopus_dept in entry["departments"] else entry["departments"][0]
        return dept, "directory"
    if config.FACULTY_OF.get(scopus_dept or "") == entry["faculty"]:
        return scopus_dept, "directory (faculty) + scopus"
    return config.not_stated(entry["faculty"]), "directory (faculty)"


def build(atlas: dict, name_parts: dict, overrides: dict, reference_year: int,
          recent_years: int, min_recent: int, directory: Directory | None = None,
          unconfirmed_years: int | None = None, unconfirmed_min: int | None = None) -> dict:
    authors = {a["scopus_id"]: a for a in atlas["authors"]}
    papers = atlas["papers"]
    recent_from = reference_year - recent_years + 1
    unconfirmed_from = reference_year - (unconfirmed_years or recent_years) + 1
    unconfirmed_min = unconfirmed_min if unconfirmed_min is not None else min_recent

    dir_match = {}
    for auid, a in authors.items():
        surname, given = name_parts.get(auid) or split_name(a["name"])
        entry, score = directory.match(surname, given, a["department"]) if directory else (None, 0)
        if entry:
            dir_match[auid] = (entry, score)

    uf, merge_log, candidates = find_merges(authors, papers, name_parts, overrides, dir_match)
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
            if authors[i]["department"]:
                dept_votes[authors[i]["department"]] += len(authors[i]["papers"])
        ranked = [d for d, _ in dept_votes.most_common()]
        real = [d for d in ranked if d not in NOT_STATED_KEYS]
        scopus_dept = (real or ranked or [None])[0]
        matches = sorted((dir_match[i] for i in members if i in dir_match),
                         key=lambda m: -m[1])
        entry, score = matches[0] if matches else (None, 0)
        dept, source = place(scopus_dept, entry)
        paper_ids = sorted({p for i in members for p in authors[i]["papers"]},
                           key=lambda p: (-(year_of(papers[p]) or 0), p))
        years = [y for p in paper_ids if (y := year_of(papers[p]))]
        dept = ov.get("department") or dept
        people[main_id] = {
            "scopus_id": main_id,
            "scopus_ids": members,
            "name": ov.get("name") or (entry["name"] if entry and score >= 2 else authors[main_id]["name"]),
            "orcid": next((authors[i]["orcid"] for i in members if authors[i].get("orcid")), None),
            "faculty": config.FACULTY_OF.get(dept or ""),
            "department": dept,
            "position": ({"nb": entry.get("position_nb"), "en": entry.get("position_en")}
                         if entry and not entry["excluded"] else None),
            "uis_links": ({"nb": entry.get("url_nb"), "en": entry.get("url_en")}
                          if entry and not entry["excluded"] else None),
            "paper_ids": paper_ids,
            "n_publications": len(paper_ids),
            "n_recent": sum(1 for y in years if y >= recent_from),
            "citations": sum(papers[p]["citations"] for p in paper_ids),
            "pubs_per_year": dict(sorted(Counter(str(y) for y in years).items())),
            "first_year": min(years, default=None),
            "last_year": max(years, default=None),
            "_include_override": ov.get("include"),
            "_confirmed": entry is not None and not entry["excluded"],
            "_source": "override" if ov.get("department") else source,
            "_directory": (entry["name"], score) if entry else None,
            "_n_unconfirmed_recent": sum(1 for y in years if y >= unconfirmed_from),
            "_affiliations": [s for i in members for s in authors[i].get("affiliation_strings", [])],
        }
        for i in members:
            canon[i] = main_id

    for pid, person in people.items():
        forced = person.pop("_include_override")
        if forced is not None:
            person["included"] = forced and person["department"] is not None
        elif not person["department"]:
            person["included"] = False
        elif person["_confirmed"]:
            person["included"] = person["n_recent"] >= min_recent
        else:
            person["included"] = person["_n_unconfirmed_recent"] >= unconfirmed_min

    for pid, person in people.items():
        if not person["included"]:
            continue
        kw_count, kw_spellings = Counter(), defaultdict(Counter)
        co_count, dept_count = Counter(), Counter()
        for p in person["paper_ids"]:
            for k in papers[p]["keywords"]:
                kw_count[k.lower()] += 1
                kw_spellings[k.lower()][k] += 1
            co = {canon[c] for c in papers[p]["coauthor_ids"] if c in canon} - {pid}
            co_count.update(c for c in co if people[c]["included"])
            dept_count.update({people[c]["department"] for c in co}
                              - {person["department"], None} - NOT_STATED_KEYS)
        person["keywords"] = [
            [max(kw_spellings[k].items(), key=lambda s: (s[1], sum(c.isupper() for c in s[0])))[0], n]
            for k, n in kw_count.most_common(30)]
        person["top_coauthors"] = [
            {"scopus_id": c, "name": people[c]["name"], "n_papers": n}
            for c, n in co_count.most_common(10)]
        person["collab_departments"] = dict(dept_count.most_common())

    return {"people": people, "merge_log": merge_log, "candidates": candidates,
            "recent_from": recent_from, "unconfirmed_from": unconfirmed_from,
            "directory_matched": {e["id"] for e, _ in dir_match.values()}}


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
    if config.DIRECTORY.exists():
        dir_data = json.loads(config.DIRECTORY.read_text(encoding="utf-8"))
        print(f"UiS employee directory from {dir_data['generated'][:10]}: "
              f"{len(dir_data['employees'])} employees.")
    else:
        dir_data = None
        print("No employee directory yet (run pipeline/collect_directory.py) – "
              "everyone is treated as unconfirmed.")
    directory = Directory(dir_data)

    res = build(atlas, name_parts, overrides, config.REFERENCE_YEAR,
                config.RECENT_YEARS, config.MIN_RECENT_PUBLICATIONS, directory,
                config.UNCONFIRMED_RECENT_YEARS, config.UNCONFIRMED_MIN_RECENT_PUBLICATIONS)
    people = res["people"]
    included = [p for p in people.values() if p["included"]]
    included.sort(key=lambda p: (p["faculty"], p["department"], p["name"]))

    config.INTERIM.mkdir(parents=True, exist_ok=True)
    out = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "reference_year": config.REFERENCE_YEAR,
        "recent_from": res["recent_from"],
        "min_recent_publications": config.MIN_RECENT_PUBLICATIONS,
        "unconfirmed_from": res["unconfirmed_from"],
        "unconfirmed_min_recent_publications": config.UNCONFIRMED_MIN_RECENT_PUBLICATIONS,
        "researchers": [{k: v for k, v in p.items() if not k.startswith("_") and k != "included"}
                        for p in included],
    }
    config.PROFILES.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    config.MERGE_LOG.write_text(json.dumps(res["merge_log"], ensure_ascii=False, indent=1),
                                encoding="utf-8")

    # ---- review files for the project owner
    listed = [p for p in people.values() if p["department"] or p["_directory"]]
    write_csv(config.REVIEW_DIR / "researchers.csv",
              ["status", "scopus_id", "other_scopus_ids", "name", "faculty", "department",
               "department_source", "directory_name", "directory_match", "position",
               "n_publications", f"n_since_{res['recent_from']}", "last_year",
               "affiliation_example", "scopus_url"],
              [["included" if p["included"] else "dropped", p["scopus_id"],
                " ".join(p["scopus_ids"][1:]), p["name"], p["faculty"], p["department"],
                p["_source"], (p["_directory"] or ["", ""])[0], (p["_directory"] or ["", ""])[1],
                (p["position"] or {}).get("nb"), p["n_publications"], p["n_recent"], p["last_year"],
                (p["_affiliations"] or [""])[0], SCOPUS_AUTHOR_URL.format(p["scopus_id"])]
               for p in sorted(listed, key=lambda p: (not p["included"], p["faculty"] or "~",
                                                      p["department"] or "", p["name"]))])
    unmatched = sorted((p for p in people.values()
                        if not p["department"] and not p["_directory"] and p["_affiliations"]),
                       key=lambda p: -p["n_recent"])
    write_csv(config.REVIEW_DIR / "unmatched_uis_authors.csv",
              ["scopus_id", "name", "n_papers_total", f"n_since_{res['recent_from']}",
               "affiliation_strings", "scopus_url"],
              [[p["scopus_id"], p["name"], p["n_publications"], p["n_recent"],
                " || ".join(p["_affiliations"]), SCOPUS_AUTHOR_URL.format(p["scopus_id"])]
               for p in unmatched])
    if dir_data:
        staff = [e for e in directory.entries if e["departments"] and e["id"] not in res["directory_matched"]]
        write_csv(config.REVIEW_DIR / "directory_staff_without_scopus.csv",
                  ["name", "department", "position", "uis_profile"],
                  [[e["name"], e["departments"][0], e.get("position_nb"), e.get("url_nb")]
                   for e in sorted(staff, key=lambda e: (e["departments"][0], e["name"]))])
    write_csv(config.REVIEW_DIR / "possible_duplicates.csv",
              ["scopus_id_1", "name_1", "department_1", "scopus_id_2", "name_2", "department_2",
               "shared_coauthors"],
              [[c["ids"][0], c["names"][0], c["departments"][0],
                c["ids"][1], c["names"][1], c["departments"][1], c["shared_coauthors"]]
               for c in res["candidates"]])

    # ---- report
    confirmed = sum(1 for p in included if p["_confirmed"])
    print(f"{len(atlas['authors'])} Scopus author IDs → {len(people)} people after "
          f"{len(res['merge_log'])} merges ({len(res['candidates'])} possible duplicates left for review).")
    rule = (f"≥{config.MIN_RECENT_PUBLICATIONS} papers since {res['recent_from']}"
            if config.MIN_RECENT_PUBLICATIONS else "all")
    print(f"Included: {len(included)} – {confirmed} confirmed in the employee directory "
          f"({rule}), "
          f"{len(included) - confirmed} from Scopus only "
          f"(≥{config.UNCONFIRMED_MIN_RECENT_PUBLICATIONS} since {res['unconfirmed_from']}).\n")
    by_faculty = defaultdict(Counter)
    for p in included:
        by_faculty[p["faculty"]][p["department"]] += 1
    for f in config.FACULTIES:
        depts = by_faculty.get(f["name"], Counter())
        print(f"  {sum(depts.values()):4d}  {f['name']}")
        for dept, n in depts.most_common():
            print(f"        {n:4d}  {dept}")
    years_by_person = {pid: [y for p in person["paper_ids"] if (y := year_of(atlas["papers"][p]))]
                       for pid, person in people.items() if person["department"]}
    print("\nPeople with a department under other inclusion rules (for tuning config.py):")
    print("\n".join(threshold_table(years_by_person, config.REFERENCE_YEAR)))
    print(f"\nWrote {config.PROFILES.name}, {config.MERGE_LOG.name} and review CSVs in "
          f"{config.REVIEW_DIR} (local only, never commit).")


if __name__ == "__main__":
    main()
