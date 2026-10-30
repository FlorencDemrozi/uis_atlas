#!/usr/bin/env python3
"""
Stage 1e – Publications of atlas researchers at other affiliations, and their Scopus
author metrics.

Run on the UiS network (campus or VPN), like collect_scopus.py, after it. Resumable.

collect_scopus.py finds UiS publications (affiliation search). A researcher's papers
from earlier employers are missing there, so profiles, career age and matching saw
only part of their work. This stage, for every Scopus author id of the atlas
researchers (config.PROFILES, or all UiS authors on a first run):

  1. Search – their publications without a UiS affiliation since ATLAS_FIRST_YEAR
     (AU-ID(...) AND NOT AF-ID(UiS), config.AUTHOR_BATCH ids per query); papers
     with a UiS affiliation are already in docs.jsonl. Ids searched before only
     get the last config.SCOPUS_REFRESH_YEARS years again; new ids get everything.
  2. Metrics – document count, citations and h-index of each author profile, as
     shown on Scopus (Author Retrieval API, METRICS view), refreshed every run.

Output (licensed, local only, never commit): config.RAW_AUTHOR_DOCS,
config.RAW_AUTHOR_METRICS. Then run: python pipeline/collect_scopus.py --build-only
(run_weekly.py does this).
"""
import json
import sys
from datetime import date, datetime

import collect_scopus as cs
import config

AUTHOR_URL = "https://api.elsevier.com/content/author"
REFRESH_FROM = max(config.FIRST_YEAR, date.today().year - config.SCOPUS_REFRESH_YEARS + 1)


def author_ids() -> list[str]:
    """Scopus author ids of the atlas researchers (all UiS authors before profiles exist)."""
    if config.PROFILES.exists():
        people = json.loads(config.PROFILES.read_text(encoding="utf-8"))["researchers"]
        return sorted({i for r in people for i in r["scopus_ids"]})
    atlas = json.loads(config.RAW_ATLAS.read_text(encoding="utf-8"))
    return sorted({a["scopus_id"] for a in atlas["authors"]})


def query(ids: list[str], from_year: int) -> str:
    who = " OR ".join(f"AU-ID({i})" for i in ids)
    return f"({who}) AND NOT AF-ID({config.AFID}) AND PUBYEAR > {from_year - 1}"


def batches(ids: list[str]) -> list[list[str]]:
    n = config.AUTHOR_BATCH
    return [ids[k:k + n] for k in range(0, len(ids), n)]


def phase_search(s, ids: list[str]) -> None:
    """Full search for ids never searched, refresh of recent years for the others.
    The state records which ids are done and the cursor of the batch in progress."""
    path = config.RAW_AUTHOR_STATE
    state = json.loads(path.read_text()) if path.exists() else {}
    if state.get("from_year") != config.FIRST_YEAR:   # scope changed: search everyone again
        state = {"from_year": config.FIRST_YEAR, "done": [], "current": None}
    save = lambda: path.write_text(json.dumps(state))
    done = set(state["done"])
    new = [i for i in ids if i not in done]
    print(f"Phase 1: publications at other affiliations – {len(new)} author ids to search, "
          f"{len(ids) - len(new)} to refresh ({REFRESH_FROM}–)")
    for group in batches(new):
        cur = state.get("current")
        if not cur or cur["ids"] != group:
            state["current"] = cur = {"ids": group, "cursor": "*", "done": False, "count": 0}
        cs.search(s, query(group, config.FIRST_YEAR), cur, config.RAW_AUTHOR_DOCS, save)
        state["done"] += group
        state["current"] = None
        save()
    old = [i for i in ids if i in done]
    if not old:
        return
    if state.get("refreshed") == date.today().isoformat():
        print("  Recent years already refreshed today.")
        return
    config.RAW_AUTHOR_REFRESH.unlink(missing_ok=True)
    config.RAW_AUTHOR_DOCS.touch()
    for group in batches(old):
        cur = {"cursor": "*", "done": False, "count": 0}
        cs.search(s, query(group, REFRESH_FROM), cur, config.RAW_AUTHOR_REFRESH, lambda: None)
    if config.RAW_AUTHOR_REFRESH.exists():
        added, total = cs.merge_refresh(config.RAW_AUTHOR_DOCS, config.RAW_AUTHOR_REFRESH)
        print(f"  Refresh complete: {added} new publications, {total} in total.")
    state["refreshed"] = date.today().isoformat()
    save()


def parse_metrics(data: dict) -> dict[str, dict]:
    """{author id: {"documents", "citations", "cited_by", "h_index"}} from an Author Retrieval answer."""
    out = {}
    data = data or {}
    # Several ids: {"author-retrieval-response-list": {"author-retrieval-response": [...]}}; one id: no list level.
    records = (data.get("author-retrieval-response-list") or data).get("author-retrieval-response")
    for rec in cs.as_list(records):
        core = rec.get("coredata") or {}
        ident = str(core.get("dc:identifier") or "").replace("AUTHOR_ID:", "")
        if not ident:
            continue
        num = lambda v: int(v) if str(v or "").isdigit() else None
        out[ident] = {"documents": num(core.get("document-count")), "citations": num(core.get("citation-count")),
                      "cited_by": num(core.get("cited-by-count")), "h_index": num(rec.get("h-index"))}
    return out


def phase_metrics(s, ids: list[str]) -> None:
    path = config.RAW_AUTHOR_METRICS
    metrics = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    print(f"Phase 2: Scopus author metrics for {len(ids)} author ids")
    got = 0
    for group in batches(ids):
        found = parse_metrics(cs.get(s, AUTHOR_URL, {"author_id": ",".join(group), "view": "METRICS"}))
        stamp = datetime.now().isoformat(timespec="seconds")
        for i, m in found.items():
            metrics[i] = dict(m, fetched=stamp)
        got += len(found)
        path.write_text(json.dumps(metrics, indent=1), encoding="utf-8")
    print(f"  {got} author profiles read ({len(ids) - got} not returned by Scopus).")


def main() -> None:
    limit = next((int(a.split("=", 1)[1]) for a in sys.argv if a.startswith("--limit=")), None)
    ids = author_ids()[:limit] if limit else author_ids()
    session = cs.make_session()
    phase_search(session, ids)
    phase_metrics(session, ids)
    print("Next: python pipeline/collect_scopus.py --build-only, then python pipeline/run_all.py")


if __name__ == "__main__":
    main()
