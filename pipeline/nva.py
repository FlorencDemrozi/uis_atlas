"""NVA (Nasjonalt vitenarkiv) records: trimming, UiS units and the merge with Scopus.

Used by collect_nva.py (trim) and build_profiles.py (integrate). Pure functions,
so they can be tested without network access.

An NVA output that is also in Scopus (same DOI, else same normalised title and
year) becomes the Scopus paper, so nothing is counted twice. Every UiS contributor
becomes a pseudo-author "nva-<Cristin person id>" with the same fields as a Scopus
author in atlas_data.json, so build_profiles.py can merge people across sources
with its usual rules plus one more: an NVA person and a Scopus author with
compatible names on the same shared paper are the same person.
"""
import re
import unicodedata
from collections import Counter, defaultdict

import config
from departments import current_department

TRANSLIT = str.maketrans({"ø": "o", "æ": "ae", "å": "a", "ð": "d", "þ": "th", "ß": "ss", "ł": "l"})


# ---------------------------------------------------------------- records
def last_part(url: str | None) -> str:
    return (url or "").rstrip("/").rsplit("/", 1)[-1]


def norm_doi(doi: str | None) -> str | None:
    doi = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", (doi or "").strip(), flags=re.I).lower()
    return doi or None


def norm_title(title: str | None) -> str:
    text = unicodedata.normalize("NFKD", (title or "").lower().translate(TRANSLIT))
    return "".join(c for c in text if c.isalnum())


def trim(hit: dict) -> dict:
    """The fields the atlas uses from one search hit. Only UiS contributors with a
    Cristin person id are kept (unverified names cannot be linked to anyone)."""
    e = hit.get("entityDescription") or {}
    ref = e.get("reference") or {}
    ctx = ref.get("publicationContext") or {}
    contributors = []
    for c in e.get("contributors") or []:
        ident = c.get("identity") or {}
        units = sorted({last_part(a.get("id")) for a in c.get("affiliations") or []
                        if last_part(a.get("id")).startswith("217.")})
        if ident.get("id") and units:
            contributors.append({"id": last_part(ident["id"]), "name": ident.get("name") or "",
                                 "role": (c.get("role") or {}).get("type"), "units": units})
    return {
        "id": hit.get("identifier"),
        "type": (ref.get("publicationInstance") or {}).get("type"),
        "title": e.get("mainTitle") or "",
        "year": str((e.get("publicationDate") or {}).get("year") or ""),
        "doi": norm_doi(ref.get("doi")),
        "venue": ctx.get("name") or (ctx.get("series") or {}).get("name"),
        "abstract": e.get("abstract"),
        "tags": [t for t in e.get("tags") or [] if isinstance(t, str)],
        "n_authors": e.get("contributorsCount") or len(e.get("contributors") or []),
        "contributors": contributors,
    }


# ---------------------------------------------------------------- units
def unit_department(units: list[str]) -> str | None:
    """Atlas department for a contributor's UiS units; a faculty's "not stated" key
    if only the faculty is known; None for units outside the atlas (museum,
    national centres, administration)."""
    def lookup(table: dict) -> list[str]:
        found = []
        for u in units:
            parts = u.split(".")
            for n in range(len(parts), 1, -1):
                if ".".join(parts[:n]) in table:
                    found.append(table[".".join(parts[:n])])
                    break
        return found
    depts = lookup(config.NVA_DEPARTMENTS)
    if depts:
        return Counter(depts).most_common(1)[0][0]
    faculties = lookup(config.NVA_FACULTIES)
    return config.not_stated(faculties[0]) if faculties else None


# ---------------------------------------------------------------- names
def name_tokens(name: str) -> list[str]:
    text = unicodedata.normalize("NFKD", (name or "").lower().translate(TRANSLIT))
    text = "".join(c if c.isalnum() else " " for c in text if not unicodedata.combining(c))
    return text.split()


def names_compatible(a: str, b: str) -> bool:
    """'Klaus Mohn' ~ 'Klaus B. Mohn' ~ 'K. Mohn' ~ 'Lars Klaus Mohn', but not
    'Kari Mohn'; Norwegian double surnames are allowed ('Kari Berge' ~ 'Kari Berge
    Hansen'). The surname of one appears in the other's name, and they share a given
    name (or its initial, when one side gives initials only)."""
    ta, tb = name_tokens(a), name_tokens(b)
    if len(ta) < 2 or len(tb) < 2 or not (ta[-1] in tb[1:] or tb[-1] in ta[1:]):
        return False
    ga, gb = ta[:-1], tb[:-1]
    if all(len(t) == 1 for t in ga) or all(len(t) == 1 for t in gb):
        return bool({t[0] for t in ga} & {t[0] for t in gb})
    return bool({t for t in ga if len(t) > 1} & {t for t in gb if len(t) > 1})


# ---------------------------------------------------------------- merge
def integrate(atlas: dict, records: list[dict]) -> tuple[dict, list[tuple[str, str]], dict]:
    """Atlas with NVA outputs and NVA people added, the (NVA id, Scopus id) pairs
    that are the same person, and counts for the report."""
    papers = {eid: dict(p, category=config.category_of(p.get("type")), source="scopus")
              for eid, p in atlas["papers"].items()}
    scopus_authors = {a["scopus_id"]: a for a in atlas["authors"]}
    by_doi = {norm_doi(p.get("doi")): eid for eid, p in papers.items() if p.get("doi")}
    by_title = {(norm_title(p["title"]), str(p.get("year"))): eid for eid, p in papers.items()
                if len(norm_title(p["title"])) >= 20}

    people = {}
    votes = defaultdict(Counter)
    stats = Counter()
    seen = set()
    for r in records:
        if r["id"] in seen or r["type"] in config.NVA_SKIPPED_TYPES:
            continue
        seen.add(r["id"])
        contributors = [c for c in r["contributors"] if c["role"] not in config.NVA_SKIPPED_ROLES]
        if not contributors:
            stats["no UiS contributor"] += 1
            continue
        nt = norm_title(r["title"])
        eid = by_doi.get(r["doi"]) if r["doi"] else None
        if eid is None and len(nt) >= 20:
            y = int(r["year"]) if r["year"].isdigit() else 0
            eid = next((by_title[k] for k in [(nt, str(y)), (nt, str(y - 1)), (nt, str(y + 1))]
                        if k in by_title), None)
        if eid:
            stats["also in Scopus"] += 1
            papers[eid]["nva_id"] = r["id"]
            pid = eid
        else:
            stats["NVA only"] += 1
            pid = f"nva-{r['id']}"
            papers[pid] = {
                "title": r["title"], "year": r["year"], "venue": r["venue"], "type": r["type"],
                "doi": r["doi"], "citations": None, "keywords": r["tags"], "abstract": r["abstract"],
                "n_authors": r["n_authors"], "coauthor_ids": [], "category": config.category_of(r["type"]),
                "source": "nva", "url": config.NVA_PUBLICATION_URL.format(r["id"]),
            }
        for c in contributors:
            aid = f"nva-{c['id']}"
            person = people.setdefault(aid, {"names": Counter(), "papers": set(), "observed": []})
            person["names"][c["name"]] += 1
            person["papers"].add(pid)
            person["observed"].append((int(r["year"]) if r["year"].isdigit() else None,
                                       unit_department(c["units"])))
            twins = [a for a in papers[pid]["coauthor_ids"]
                     if a in scopus_authors and names_compatible(c["name"], scopus_authors[a]["name"])]
            if eid and len(twins) == 1:
                votes[aid][twins[0]] += 1
            elif aid not in papers[pid]["coauthor_ids"]:
                papers[pid]["coauthor_ids"].append(aid)

    links = []
    for aid, v in votes.items():
        (best, n), *rest = v.most_common()
        if not rest or n > rest[0][1]:
            links.append((aid, best))
    authors = list(atlas["authors"])
    for aid, person in people.items():
        pids = sorted(person["papers"])
        authors.append({
            "scopus_id": aid, "cristin_id": aid[4:], "source": "nva",
            "name": person["names"].most_common(1)[0][0], "orcid": None,
            "papers": pids, "uis_papers": pids, "affiliation_strings": [],
            "department": current_department(person["observed"]),
        })
    stats["NVA people"] = len(people)
    stats["linked to Scopus"] = len(links)
    return {**atlas, "papers": papers, "authors": authors}, links, dict(stats)
