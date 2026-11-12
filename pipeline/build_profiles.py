#!/usr/bin/env python3
"""
Stage 2 – Build one profile per researcher.

Input:  config.RAW_ATLAS and config.RAW_DOCS (from collect_scopus.py),
        config.RAW_NVA (from collect_nva.py, optional),
        config.DIRECTORY (from collect_directory.py, optional),
        config/overrides.json
Output: config.PROFILES, config.PAPERS (Scopus and NVA papers merged),
        config.MERGE_LOG, review CSVs in config.REVIEW_DIR
        (all licensed or personal data – local only, never commit)

Steps:
- Add NVA outputs and people (pipeline/nva.py): an output also in Scopus becomes
  the Scopus paper; NVA-only outputs (books, chapters, reports, artistic work,
  lectures, ...) get id "nva-<identifier>", NVA people "nva-<Cristin id>". The
  steps below treat NVA people like Scopus author IDs; a person found only in
  NVA keeps the "nva-" id as profile id.
- Match each Scopus author to the UiS employee directory by name (see
  pipeline/directory.py). A match confirms the person as current staff and
  gives today's department, position and UiS profile link. Staff listed only in
  excluded units (national centres, museum, divisions) are left out.
- Merge duplicate Scopus author IDs for the same person: forced merges from
  overrides, an NVA person with a compatible name on a paper shared with Scopus,
  same ORCID, the same directory person, or same normalised name +
  department + a shared co-author. Name-only matches are not merged but listed
  for review.
- Department: override, else directory, else Scopus affiliations.
- Researchers in config/exclusions.json (any of their merged ids) are left out
  entirely, so later stages (summaries, funding matches) never see their data.
- Profile id: a Scopus id (the one with most papers) whenever the person has one;
  an id that was already a profile id in the previous profiles.json is kept, so
  ids (and the summaries cached under them) do not flip between runs.
- Keep researchers with enough recent papers: confirmed staff need
  config.MIN_RECENT_PUBLICATIONS in config.RECENT_YEARS years (0: all current
  staff with a Scopus profile), others the stricter config.UNCONFIRMED_* rule,
  counting UiS papers only (overrides can force include/exclude).
- Compute per researcher: faculty, department, position, paper ids (newest
  first; all affiliations since ATLAS_FIRST_YEAR, see collect_scopus_authors.py),
  counts per output category (config.OUTPUT_CATEGORIES; "publications" are
  config.PUBLICATION_CATEGORIES), how many publications have a UiS affiliation, citations, publications per year,
  keywords, UiS co-authors, collaborating departments, first/last active year,
  and the Scopus author metrics (documents, citations, h-index as on Scopus).

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
import nva
from directory import Directory
from fsutil import read_jsonl, write_text

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


def is_nva(author_id: str) -> bool:
    return author_id.startswith("nva-")


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
                dir_match: dict | None = None, links: list | None = None):
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

    for nva_id, scopus_id in links or []:
        if nva_id in authors and scopus_id in authors:
            merge([scopus_id, nva_id], "same paper in NVA and Scopus")

    by_orcid = defaultdict(list)
    for auid, a in authors.items():
        if a.get("orcid"):
            by_orcid[a["orcid"]].append(auid)
    for ids in by_orcid.values():
        if len(ids) > 1:
            merge(ids, "same ORCID")

    # Several Scopus IDs (or an NVA person) with a good name match to the same current
    # employee. Two Scopus IDs on the same paper are different people; an NVA person
    # and a Scopus ID on the same paper are rather one person seen by both sources.
    by_employee = defaultdict(list)
    for auid, (entry, score) in dir_match.items():
        if score >= 2:
            by_employee[entry["id"]].append(auid)
    for ids in by_employee.values():
        for x, y in combinations(ids, 2):
            if is_nva(x) != is_nva(y) or not set(authors[x]["papers"]) & set(authors[y]["papers"]):
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
def fullest_name(names: list[str]) -> str:
    """The most complete of a person's Scopus names ("Lennart Vogt" over "L. Vogt");
    names come with the profile with most papers first, which wins a tie."""
    return max((n for n in names if n), key=lambda n: (len(n.replace(".", "").split()[0]), len(n)), default=names[0])


def year_of(paper: dict) -> int | None:
    y = str(paper.get("year") or "")
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


def cristin_unit(units: list[dict]) -> dict | None:
    """A directory-like entry (see place()) for the atlas unit of active Cristin affiliations."""
    for table, kind in ((config.NVA_DEPARTMENTS, "dept"), (config.NVA_FACULTIES, "faculty")):
        for a in units:
            parts = a["unit"].split(".")
            for n in range(len(parts), 1, -1):
                name = table.get(".".join(parts[:n]))
                if name and kind == "dept":
                    return {"departments": [name], "faculty": config.FACULTY_OF[name], "excluded": False}
                if name:
                    return {"departments": [], "faculty": name, "excluded": False}
    return None   # institution level or a unit outside the faculties: keep the Scopus department


def staff_status(confirmed: bool, record: dict | None) -> tuple[str, list[dict]]:
    """("current" | "former" | "unknown", active UiS affiliations) from the employee
    directory and the person's Cristin record (collect_cristin.py)."""
    active = [a for a in (record or {}).get("uis", []) if a["active"]]
    if confirmed or active:
        return "current", active
    return ("former" if record and record.get("uis") else "unknown"), []


def build(atlas: dict, name_parts: dict, overrides: dict, reference_year: int,
          recent_years: int, min_recent: int, directory: Directory | None = None,
          unconfirmed_years: int | None = None, unconfirmed_min: int | None = None,
          links: list | None = None, excluded: set | None = None,
          previous_ids: set | None = None, cristin: dict | None = None,
          cristin_include_min: int | None = None) -> dict:
    excluded, previous_ids, cristin = excluded or set(), previous_ids or set(), cristin or {}
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

    uf, merge_log, candidates = find_merges(authors, papers, name_parts, overrides, dir_match, links)
    clusters = defaultdict(list)
    for auid in authors:
        clusters[uf.find(auid)].append(auid)

    people, canon = {}, {}
    for members in clusters.values():
        # A Scopus ID is the profile id whenever the person has one; a previous profile
        # id is kept so the id does not flip when another member gains papers.
        members.sort(key=lambda i: (is_nva(i), i not in previous_ids, -len(authors[i]["papers"])))
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
        in_directory = entry is not None and not entry["excluded"]
        cristin_id = next((authors[i]["cristin_id"] for i in members if is_nva(i)), None)
        status, active = staff_status(in_directory, cristin.get(str(cristin_id)) if cristin_id else None)
        by_cristin = status == "current" and not in_directory
        dept, source = (place(scopus_dept, entry) if not by_cristin
                        else place(scopus_dept, cristin_unit(active)))
        if by_cristin:
            source = "cristin" if source == "directory" else source.replace("directory", "cristin")
        paper_ids = sorted({p for i in members for p in authors[i]["papers"]},
                           key=lambda p: (-(year_of(papers[p]) or 0), p))
        pub_ids = [p for p in paper_ids if config.is_publication(papers[p])]
        years = [y for p in pub_ids if (y := year_of(papers[p]))]
        all_years = [y for p in paper_ids if (y := year_of(papers[p]))]
        # Papers with a UiS affiliation (older atlas_data.json: all papers were UiS papers).
        uis_ids = {p for i in members for p in authors[i].get("uis_papers", authors[i]["papers"])}
        uis_years = [y for p in uis_ids if config.is_publication(papers[p]) and (y := year_of(papers[p]))]
        # Scopus's own figures for the author profile with the most documents.
        metrics = max((authors[i]["scopus_metrics"] for i in members if authors[i].get("scopus_metrics")),
                      key=lambda m: m.get("documents") or 0, default=None)
        dept = ov.get("department") or dept
        people[main_id] = {
            "scopus_id": main_id,
            "scopus_ids": members,
            "cristin_id": cristin_id,
            "name": ov.get("name") or (entry["name"] if entry and score >= 2 else fullest_name(
                [authors[i]["name"] for i in members])),
            "orcid": next((authors[i]["orcid"] for i in members if authors[i].get("orcid")), None),
            "faculty": config.FACULTY_OF.get(dept or ""),
            "department": dept,
            "position": ({"nb": entry.get("position_nb"), "en": entry.get("position_en")}
                         if in_directory else
                         {"nb": active[0].get("nb") or active[0].get("en"),
                          "en": active[0].get("en") or active[0].get("nb")}
                         if active and (active[0].get("nb") or active[0].get("en")) else None),
            # current: in the employee directory or an active UiS affiliation in Cristin;
            # former: Cristin shows only ended UiS affiliations; unknown: neither.
            "staff": status,
            "uis_links": ({"nb": entry.get("url_nb"), "en": entry.get("url_en")}
                          if entry and not entry["excluded"] else None),
            "email": entry.get("email") if entry and not entry["excluded"] else None,
            "paper_ids": paper_ids,
            "n_publications": len(pub_ids),
            "n_uis": sum(1 for p in pub_ids if p in uis_ids),
            "output_types": dict(Counter(papers[p].get("category", "article") for p in paper_ids).most_common()),
            "other_paper_ids": [p for p in paper_ids if p not in uis_ids],
            "scopus_metrics": metrics,
            "n_recent": sum(1 for y in years if y >= recent_from),
            "citations": sum(int(papers[p]["citations"] or 0) for p in paper_ids),
            "pubs_per_year": dict(sorted(Counter(str(y) for y in years).items())),
            "first_year": min(all_years, default=None),
            "last_year": max(all_years, default=None),
            "_include_override": ov.get("include"),
            "_excluded": bool(excluded & set(members)),
            "_confirmed": in_directory,
            "_by_cristin": by_cristin,
            "_source": "override" if ov.get("department") else source,
            "_directory": (entry["name"], score) if entry else None,
            # Not in the UiS directory (may have left): only UiS papers count, so work at
            # a new employer does not keep someone in the atlas.
            "_n_unconfirmed_recent": sum(1 for y in uis_years if y >= unconfirmed_from),
            "_affiliations": [s for i in members for s in authors[i].get("affiliation_strings", [])],
        }
        for i in members:
            canon[i] = main_id

    for pid, person in people.items():
        forced = person.pop("_include_override")
        if person["_excluded"]:   # opted out (config/exclusions.json): never in profiles.json
            person["included"] = False
        elif forced is not None:
            person["included"] = forced and person["department"] is not None
        elif not person["department"]:
            person["included"] = False
        elif person["_confirmed"]:
            person["included"] = person["n_recent"] >= min_recent
        elif person["_by_cristin"] and cristin_include_min is not None:   # config.CRISTIN_INCLUDE_MIN
            person["included"] = person["n_recent"] >= cristin_include_min
        else:
            person["included"] = person["_n_unconfirmed_recent"] >= unconfirmed_min

    for pid, person in people.items():
        if not person["included"]:
            continue
        kw_count, kw_spellings = Counter(), defaultdict(Counter)
        co_count, dept_count = Counter(), Counter()
        for p in person["paper_ids"]:
            for k in papers[p]["keywords"] or []:
                kw_count[k.lower()] += 1
                kw_spellings[k.lower()][k] += 1
            co = {canon[c] for c in papers[p]["coauthor_ids"] if c in canon} - {pid}
            co_count.update(c for c in sorted(co) if people[c]["included"])   # sorted: ties in a stable order
            dept_count.update(sorted({people[c]["department"] for c in co}
                                     - {person["department"], None} - NOT_STATED_KEYS))
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


def check_overrides(overrides: dict) -> None:
    """Stop with a clear message if an override names a department the atlas does not know."""
    bad = [(auid, ov["department"]) for auid, ov in overrides.items()
           if ov.get("department") and ov["department"] not in config.FACULTY_OF]
    if bad:
        raise SystemExit("config/overrides.json: unknown department(s) – use a department name from "
                         "config.FACULTIES:\n" + "\n".join(f"  author {a}: {d!r}" for a, d in bad))


def previous_profile_ids() -> set[str]:
    """Profile ids of the last run (empty if there is none or it cannot be read)."""
    try:
        return {r["scopus_id"] for r in json.loads(config.PROFILES.read_text(encoding="utf-8"))["researchers"]}
    except (OSError, ValueError, KeyError, TypeError):
        return set()


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
    for e in read_jsonl(config.RAW_DOCS):
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


def load_nva() -> list[dict]:
    records = []
    for path in sorted(config.RAW_NVA.glob("*.jsonl")) if config.RAW_NVA.exists() else []:
        records.extend(read_jsonl(path))
    return records


def profile_url(person: dict) -> str:
    if is_nva(person["scopus_id"]):
        return config.NVA_PERSON_URL.format(person["scopus_id"][4:])
    return SCOPUS_AUTHOR_URL.format(person["scopus_id"])


def main() -> None:
    atlas = json.loads(config.RAW_ATLAS.read_text(encoding="utf-8"))
    nva_records = load_nva()
    if nva_records:
        atlas, links, nva_stats = nva.integrate(atlas, nva_records)
        print("NVA: " + ", ".join(f"{v} {k}" for k, v in nva_stats.items()) + ".")
    else:
        links = []
        print("No NVA data yet (run pipeline/collect_nva.py) – Scopus only.")
    overrides = json.loads(config.OVERRIDES.read_text(encoding="utf-8")).get("authors", {})
    check_overrides(overrides)
    excluded = set(json.loads(config.EXCLUSIONS.read_text(encoding="utf-8")).get("scopus_ids", []))
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
    cristin = (json.loads(config.RAW_CRISTIN.read_text(encoding="utf-8")).get("persons", {})
               if config.RAW_CRISTIN.exists() else {})
    print(f"Cristin person records: {len(cristin)} (run pipeline/collect_cristin.py to update).")

    res = build(atlas, name_parts, overrides, config.REFERENCE_YEAR,
                config.RECENT_YEARS, config.MIN_RECENT_PUBLICATIONS, directory,
                config.UNCONFIRMED_RECENT_YEARS, config.UNCONFIRMED_MIN_RECENT_PUBLICATIONS, links,
                excluded, previous_profile_ids(), cristin, config.CRISTIN_INCLUDE_MIN)
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
    write_text(config.PAPERS, json.dumps(atlas["papers"], ensure_ascii=False, separators=(",", ":")))
    write_text(config.MERGE_LOG, json.dumps(res["merge_log"], ensure_ascii=False, indent=1))
    write_text(config.PROFILES, json.dumps(out, ensure_ascii=False, indent=1))
    # People the directory does not confirm, with recent work: collect_cristin.py checks
    # whether their UiS affiliation is still active.
    candidates = sorted({str(p["cristin_id"]) for p in people.values()
                         if p["cristin_id"] and p["department"] and not p["_confirmed"]
                         and not p["_excluded"] and p["n_recent"] >= config.CRISTIN_MIN_RECENT_PUBLICATIONS})
    write_text(config.CRISTIN_CANDIDATES, json.dumps(candidates))

    # ---- review files for the project owner
    listed = [p for p in people.values() if p["department"] or p["_directory"]]
    write_csv(config.REVIEW_DIR / "researchers.csv",
              ["status", "staff", "scopus_id", "other_scopus_ids", "name", "faculty", "department",
               "department_source", "directory_name", "directory_match", "position",
               "n_publications", f"n_since_{res['recent_from']}", "last_year",
               "affiliation_example", "profile_url"],
              [["excluded (opt-out)" if p["_excluded"] else "included" if p["included"] else "dropped",
                p["staff"], p["scopus_id"],
                " ".join(p["scopus_ids"][1:]), p["name"], p["faculty"], p["department"],
                p["_source"], (p["_directory"] or ["", ""])[0], (p["_directory"] or ["", ""])[1],
                (p["position"] or {}).get("nb"), p["n_publications"], p["n_recent"], p["last_year"],
                (p["_affiliations"] or [""])[0], profile_url(p)]
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
    print(f"{len(atlas['authors'])} Scopus author IDs and NVA people -> {len(people)} people after "
          f"{len(res['merge_log'])} merges ({len(res['candidates'])} possible duplicates left for review).")
    n_excluded = sum(1 for p in people.values() if p["_excluded"])
    if n_excluded:
        print(f"Left out {n_excluded} researcher(s) in {config.EXCLUSIONS.name}.")
    rule = (f"≥{config.MIN_RECENT_PUBLICATIONS} papers since {res['recent_from']}"
            if config.MIN_RECENT_PUBLICATIONS else "all")
    print(f"Included: {len(included)} – {confirmed} confirmed in the employee directory "
          f"({rule}), "
          f"{len(included) - confirmed} not in the directory "
          f"(≥{config.UNCONFIRMED_MIN_RECENT_PUBLICATIONS} since {res['unconfirmed_from']}).")
    staff = Counter(p["staff"] for p in included)
    print(f"Staff status: {staff['current']} current ({sum(1 for p in included if p['_by_cristin'])} "
          f"of them from Cristin), {staff['former']} former, {staff['unknown']} unknown.\n")
    by_faculty = defaultdict(Counter)
    for p in included:
        by_faculty[p["faculty"]][p["department"]] += 1
    for f in config.FACULTIES:
        depts = by_faculty.get(f["name"], Counter())
        print(f"  {sum(depts.values()):4d}  {f['name']}")
        for dept, n in depts.most_common():
            print(f"        {n:4d}  {dept}")
    years_by_person = {pid: [y for p in person["paper_ids"] if config.is_publication(atlas["papers"][p])
                             and (y := year_of(atlas["papers"][p]))]
                       for pid, person in people.items() if person["department"]}
    print("\nPeople with a department under other inclusion rules (for tuning config.py):")
    print("\n".join(threshold_table(years_by_person, config.REFERENCE_YEAR)))
    print(f"\nWrote {config.PROFILES.name}, {config.MERGE_LOG.name} and review CSVs in "
          f"{config.REVIEW_DIR} (local only, never commit).")


if __name__ == "__main__":
    main()
