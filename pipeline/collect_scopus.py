#!/usr/bin/env python3
"""
Stage 1 – Collect publications from Scopus for the UiS Researcher Atlas.

Run on the UiS network (campus or VPN), or anywhere if SCOPUS_INSTTOKEN is set.
Reads SCOPUS_API_KEY from .env (asks if missing; a scheduled run stops instead).

Resumable: if it stops (weekly quota, network), run it again.
Once the full search is complete, every later run refreshes the last
config.SCOPUS_REFRESH_YEARS years (new papers, updated citation counts), so the
weekly run keeps the data current. --no-refresh skips that (e.g. to resume phase 2).

Phases:
  1. Search  – all UiS publications since ATLAS_FIRST_YEAR (Scopus Search API, COMPLETE view);
               afterwards a refresh of recent years on every run
  2. Details – full affiliation strings for a few papers per author, to find their
               department (Abstract Retrieval API, FULL view)
  2b. History – at least one affiliation per faculty author per period in
               config.HISTORY_PERIODS, so renamed/split departments are resolved
  3. Build   – data/raw/scopus/atlas_data.json (licensed data: local only, never commit)
               Department = most recent affiliation (see pipeline/departments.py).
               Also merges collect_scopus_authors.py's output: every paper (UiS or
               not) is credited to the UiS authors on it by author id, with "uis":
               whether they had a UiS affiliation on it; Scopus author metrics.

  python pipeline/collect_scopus.py --build-only   reruns phase 3 from the files
  already collected (no network), e.g. after changing the department mapping.
"""
import getpass
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime

import requests

from config import (AFID, FIRST_YEAR, HISTORY_PERIODS, RAW, RAW_ATLAS, RAW_AUTHOR_DOCS, RAW_AUTHOR_METRICS,
                    RAW_DETAILS, RAW_DOCS, RAW_REFRESH, RAW_SEARCH_STATE, SCOPUS_API_KEY, SCOPUS_INSTTOKEN,
                    SCOPUS_QUERY, SCOPUS_REFRESH_YEARS)
from departments import current_department, match_dept

QUERY = SCOPUS_QUERY
RAW.mkdir(parents=True, exist_ok=True)
DOCS_FILE = RAW_DOCS
SEARCH_STATE = RAW_SEARCH_STATE
DETAILS_FILE = RAW_DETAILS
FINAL_FILE = RAW_ATLAS
REFRESH_FILE = RAW_REFRESH
REFRESH_FROM = max(FIRST_YEAR, date.today().year - SCOPUS_REFRESH_YEARS + 1)
REFRESH_QUERY = f"AF-ID({AFID}) AND PUBYEAR > {REFRESH_FROM - 1}"

SEARCH_URL = "https://api.elsevier.com/content/search/scopus"
ABSTRACT_URL = "https://api.elsevier.com/content/abstract/eid/{}"
SLEEP = 0.15          # stay under Elsevier's per-second throttle
MIN_DEPT_HITS = 2     # department confirmed after this many matching papers
MAX_LOOKUPS = 3       # give up on an author's department after this many tries
MAX_PERIOD_TRIES = 2  # history: papers tried per author and period before giving up


def as_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def is_uis(afid, name):
    n = (name or "").lower()
    if "hospital" in n or "sjukehus" in n:
        return False
    return afid == AFID or "university of stavanger" in n or "universitetet i stavanger" in n


# ---------------------------------------------------------------- HTTP
def make_session():
    if not SCOPUS_API_KEY and not sys.stdin.isatty():   # scheduled run: never wait for input
        sys.exit("SCOPUS_API_KEY is not set in .env.")
    key = SCOPUS_API_KEY or getpass.getpass("Scopus API key: ").strip()
    s = requests.Session()
    s.headers.update({"X-ELS-APIKey": key, "Accept": "application/json"})
    if SCOPUS_INSTTOKEN:
        s.headers["X-ELS-Insttoken"] = SCOPUS_INSTTOKEN
    return s


def get(s, url, params):
    for attempt in range(6):
        try:
            r = s.get(url, params=params, timeout=60)
        except requests.RequestException as exc:
            print(f"  network problem ({exc}); retrying…")
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 200:
            time.sleep(SLEEP)
            return r.json()
        if r.status_code == 429:
            reset = r.headers.get("X-RateLimit-Reset")
            if reset and int(reset) - time.time() > 3600:
                sys.exit(f"\nWeekly API quota used up. Progress is saved; run again after "
                         f"{time.ctime(int(reset))}.")
            time.sleep(2 ** attempt * 2)
            continue
        if r.status_code in (401, 403):
            sys.exit(f"\nAccess denied ({r.status_code}). Check that you are on the UiS network or VPN. "
                     f"If you are, UiS may need an institutional token from Elsevier.\n{r.text[:400]}")
        if r.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        print(f"\nScopus returned {r.status_code}: {r.text[:400]}")
        r.raise_for_status()
    raise RuntimeError(f"Gave up on {url}")


# ---------------------------------------------------------------- Phase 1: search
def search(s, query, cursor_state, out_file, save):
    """Page through a search, appending records to out_file. cursor_state holds
    cursor/count/done; save() persists the state file after every page."""
    with out_file.open("a", encoding="utf-8") as f:
        while True:
            data = get(s, SEARCH_URL, {"query": query, "view": "COMPLETE",
                                       "count": 25, "cursor": cursor_state["cursor"]})
            res = data.get("search-results", {})
            entries = [e for e in as_list(res.get("entry")) if "error" not in e]
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
            f.flush()
            cursor_state["count"] += len(entries)
            nxt = res.get("cursor", {}).get("@next")
            print(f"  {cursor_state['count']} / {res.get('opensearch:totalResults', '?')} publications")
            if not entries or not nxt or nxt == cursor_state["cursor"]:
                cursor_state["done"] = True
                save()
                return
            cursor_state["cursor"] = nxt
            save()


def merge_refresh(docs_file, refresh_file):
    """Fold a finished refresh into docs_file: refreshed records replace older copies
    of the same EID and duplicates are dropped. Written to a temp file, then swapped
    in, so an interruption never loses records. Returns (new EIDs, total EIDs)."""
    docs = {}
    with docs_file.open(encoding="utf-8") as f:
        for line in f:
            docs[json.loads(line).get("eid")] = line.rstrip("\n") + "\n"
    known = set(docs)
    with refresh_file.open(encoding="utf-8") as f:
        for line in f:
            docs[json.loads(line).get("eid")] = line.rstrip("\n") + "\n"
    tmp = docs_file.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.writelines(docs.values())
    tmp.replace(docs_file)
    refresh_file.unlink()
    return len(docs.keys() - known), len(docs)


def phase_refresh(s, state):
    ref = state.get("refresh")
    if not ref or ref.get("done") or ref.get("query") != REFRESH_QUERY:
        ref = state["refresh"] = {"cursor": "*", "done": False, "count": 0, "query": REFRESH_QUERY}
        REFRESH_FILE.unlink(missing_ok=True)
    print(f"Phase 1: refreshing recent publications: {REFRESH_QUERY}")
    save = lambda: SEARCH_STATE.write_text(json.dumps(state))
    search(s, REFRESH_QUERY, ref, REFRESH_FILE, save)
    new, total = merge_refresh(DOCS_FILE, REFRESH_FILE)
    ref["finished"] = datetime.now().isoformat(timespec="seconds")
    save()
    print(f"  Refresh complete: {new} new publications, {total} in total.")


def phase_search(s, refresh=True):
    state = (json.loads(SEARCH_STATE.read_text()) if SEARCH_STATE.exists()
             else {"cursor": "*", "done": False, "count": 0, "query": QUERY})
    if state.get("query") != QUERY:
        # Scope changed (e.g. ATLAS_FIRST_YEAR): search again. Records already in
        # docs.jsonl are kept; load_docs() drops duplicates by EID.
        print("Search query changed – starting a new search (existing records are kept).")
        state = {"cursor": "*", "done": False, "count": 0, "query": QUERY}
    if state["done"]:
        print(f"Phase 1: full search already complete ({state['count']} records).")
        if refresh:
            phase_refresh(s, state)
        return
    print(f"Phase 1: searching Scopus for: {QUERY}")
    search(s, QUERY, state, DOCS_FILE, lambda: SEARCH_STATE.write_text(json.dumps(state)))


def load_docs(path=None):
    docs = {}
    path = path or DOCS_FILE
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            docs[e.get("eid")] = e
    return sorted(docs.values(), key=lambda e: e.get("prism:coverDate", ""), reverse=True)


def doc_year(entry):
    y = (entry.get("prism:coverDate") or "")[:4]
    return int(y) if y.isdigit() else None


def period_of(year):
    for i, (a, b) in enumerate(HISTORY_PERIODS):
        if year is not None and a <= year <= b:
            return i
    return None


def uis_authors(entry):
    uis_afids = {a.get("afid") for a in as_list(entry.get("affiliation"))
                 if is_uis(a.get("afid"), a.get("affilname"))}
    uis_afids.add(AFID)
    return [a for a in as_list(entry.get("author"))
            if any(x.get("$") in uis_afids for x in as_list(a.get("afid")))]


# ---------------------------------------------------------------- Phase 2: departments
def parse_author_groups(data):
    try:
        head = data["abstracts-retrieval-response"]["item"]["bibrecord"]["head"]
    except (KeyError, TypeError):
        return {}
    out = defaultdict(list)
    for g in as_list(head.get("author-group")):
        aff = g.get("affiliation") or {}
        orgs = [o.get("$", "") if isinstance(o, dict) else str(o)
                for o in as_list(aff.get("organization"))]
        src = aff.get("ce:source-text")
        if src:
            orgs.append(src if isinstance(src, str) else json.dumps(src))
        if not is_uis(str(aff.get("@afid")), " ".join(orgs)):
            continue
        for a in as_list(g.get("author")):
            if a.get("@auid"):
                out[a["@auid"]].extend(orgs)
    return out


def load_details():
    details = {}
    if DETAILS_FILE.exists():
        with DETAILS_FILE.open(encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                details[rec["eid"]] = rec["authors"]
    return details


def phase_details(s, docs):
    details = load_details()
    year = {e["eid"]: doc_year(e) for e in docs}
    hits, lookups = defaultdict(Counter), Counter()
    for eid, amap in details.items():
        for auid, orgs in amap.items():
            lookups[auid] += 1
            d = match_dept(orgs, year.get(eid))
            if d:
                hits[auid][d] += 1

    def needs(auid):
        return sum(hits[auid].values()) < MIN_DEPT_HITS and lookups[auid] < MAX_LOOKUPS

    todo = [e for e in docs if e["eid"] not in details
            and any(needs(a.get("authid")) for a in uis_authors(e))]
    print(f"Phase 2: finding departments (up to {len(todo)} detail lookups, usually far fewer)")
    done = 0
    with DETAILS_FILE.open("a", encoding="utf-8") as f:
        for e in todo:
            if not any(needs(a.get("authid")) for a in uis_authors(e)):
                continue
            amap = parse_author_groups(get(s, ABSTRACT_URL.format(e["eid"]), {"view": "FULL"}))
            f.write(json.dumps({"eid": e["eid"], "authors": amap}, ensure_ascii=False) + "\n")
            f.flush()
            details[e["eid"]] = amap
            for auid, orgs in amap.items():
                lookups[auid] += 1
                d = match_dept(orgs, year.get(e["eid"]))
                if d:
                    hits[auid][d] += 1
            done += 1
            if done % 50 == 0:
                print(f"  {done} lookups done")
    print(f"  Phase 2 complete ({done} new lookups).")
    return details


def history_gaps(docs, details):
    """Faculty authors and the periods (with papers) that have no affiliation lookup yet."""
    year = {e["eid"]: doc_year(e) for e in docs}
    faculty, covered = set(), defaultdict(set)
    for eid, amap in details.items():
        for auid, orgs in amap.items():
            if match_dept(orgs, year.get(eid)):
                faculty.add(auid)
            covered[auid].add(period_of(year.get(eid)))
    gaps = set()
    for e in docs:
        p = period_of(year[e["eid"]])
        for a in uis_authors(e):
            auid = a.get("authid")
            if p is not None and auid in faculty and p not in covered[auid]:
                gaps.add((auid, p))
    return gaps, covered, year


def phase_history(s, docs, details):
    gaps, covered, year = history_gaps(docs, details)
    print(f"Phase 2b: department history – {len(gaps)} author/period gaps to fill "
          f"(at most that many lookups; shared papers fill several)")
    tries, done = Counter(), 0
    with DETAILS_FILE.open("a", encoding="utf-8") as f:
        for e in docs:                                   # newest first
            p = period_of(year[e["eid"]])
            if e["eid"] in details or p is None:
                continue
            want = [a.get("authid") for a in uis_authors(e)
                    if (a.get("authid"), p) in gaps and tries[(a.get("authid"), p)] < MAX_PERIOD_TRIES]
            if not want:
                continue
            amap = parse_author_groups(get(s, ABSTRACT_URL.format(e["eid"]), {"view": "FULL"}))
            f.write(json.dumps({"eid": e["eid"], "authors": amap}, ensure_ascii=False) + "\n")
            f.flush()
            details[e["eid"]] = amap
            for auid in want:
                tries[(auid, p)] += 1
            for auid in amap:
                gaps.discard((auid, p))
            done += 1
            if done % 100 == 0:
                print(f"  {done} lookups done, {len(gaps)} gaps left")
    print(f"  Phase 2b complete ({done} new lookups, {len(gaps)} gaps without a usable paper).")
    return details


# ---------------------------------------------------------------- Phase 3: build
def paper_record(e):
    return {
        "title": e.get("dc:title"),
        "year": (e.get("prism:coverDate") or "")[:4],
        "venue": e.get("prism:publicationName"),
        "type": e.get("subtypeDescription"),
        "doi": e.get("prism:doi"),
        "citations": int(e.get("citedby-count") or 0),
        "keywords": [k.strip() for k in (e.get("authkeywords") or "").split("|") if k.strip()],
        "abstract": e.get("dc:description"),
        "n_authors": len(as_list(e.get("author"))),
        "coauthor_ids": [a.get("authid") for a in as_list(e.get("author"))],
    }


def build(docs, details, other_docs=(), metrics=None):
    """docs: UiS publications; other_docs: atlas researchers' publications at other
    affiliations (collect_scopus_authors.py); metrics: Scopus author metrics by id."""
    papers, authors = {}, {}
    for e in docs:
        eid = e["eid"]
        ua = uis_authors(e)
        if not ua:
            continue
        papers[eid] = paper_record(e)
        for a in ua:
            auid = a.get("authid")
            rec = authors.setdefault(auid, {
                "scopus_id": auid,
                "name": " ".join(filter(None, [a.get("given-name"), a.get("surname")])) or a.get("authname"),
                "orcid": a.get("orcid"),
                "papers": [],
                "uis_papers": [],
            })
            rec["papers"].append(eid)
            rec["uis_papers"].append(eid)
    # Work of the same people without a UiS affiliation: UiS papers on which they had
    # another affiliation (a UiS co-author put the paper in docs), and the papers
    # collect_scopus_authors.py found. Only people already known as UiS authors.
    extra = 0
    for e in list(docs) + list(other_docs):
        if (doc_year(e) or 0) < FIRST_YEAR:
            continue
        eid = e["eid"]
        for a in as_list(e.get("author")):
            rec = authors.get(a.get("authid"))
            if rec is None or eid in rec["papers"]:
                continue
            papers.setdefault(eid, paper_record(e))
            rec["papers"].append(eid)
            extra += 1
    for auid, m in (metrics or {}).items():
        if auid in authors:
            authors[auid]["scopus_metrics"] = {k: m.get(k) for k in ("documents", "citations", "h_index", "fetched")}

    year = {e["eid"]: doc_year(e) for e in docs}
    orgs_by_author, observations = defaultdict(Counter), defaultdict(list)
    for eid, amap in details.items():
        for auid, orgs in amap.items():
            orgs_by_author[auid].update(o for o in orgs if o)
            observations[auid].append((year.get(eid), match_dept(orgs, year.get(eid))))

    # Every UiS author is kept: build_profiles.py also places people through the
    # UiS employee directory when Scopus names no department ("department": None).
    matched = 0
    for auid, rec in authors.items():
        rec["affiliation_strings"] = [o for o, _ in orgs_by_author[auid].most_common(3)]
        rec["department"] = current_department(observations[auid])
        rec["department_history"] = sorted([y, d] for y, d in observations[auid] if y and d)
        matched += rec["department"] is not None

    out = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "query": QUERY,
        "authors": list(authors.values()),
        "papers": papers,
    }
    FINAL_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    n_uis = len({p for a in authors.values() for p in a["uis_papers"]})
    print(f"\nDone. {len(authors)} UiS authors ({matched} with a department from Scopus), "
          f"{len(papers)} papers ({n_uis} with a UiS affiliation; {extra} author credits from other affiliations).")
    print(f"Output (local only, never commit): {FINAL_FILE}")
    print("Next: python pipeline/collect_directory.py (if not run recently), then python pipeline/run_all.py")


if __name__ == "__main__":
    load_metrics = lambda: (json.loads(RAW_AUTHOR_METRICS.read_text(encoding="utf-8"))
                            if RAW_AUTHOR_METRICS.exists() else {})
    if "--build-only" in sys.argv:   # rebuild from files already collected, no network
        all_docs = load_docs()
        build(all_docs, load_details(), load_docs(RAW_AUTHOR_DOCS), load_metrics())
        sys.exit()
    session = make_session()
    phase_search(session, refresh="--no-refresh" not in sys.argv)
    all_docs = load_docs()
    all_details = phase_details(session, all_docs)
    all_details = phase_history(session, all_docs, all_details)
    build(all_docs, all_details, load_docs(RAW_AUTHOR_DOCS), load_metrics())
