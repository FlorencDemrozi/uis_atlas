#!/usr/bin/env python3
"""
Stage 5b – What's new: researchers and funding calls that appeared since earlier runs.

Input:  data/public/researchers.json, config.CALLS, config.CALLS_HISTORY (first run only)
State:  config.FIRST_SEEN (local only): the date each researcher key and call id was
        first seen, and the baseline date (the first run, whose items are not "new")
Output: data/public/changes.json – {"generated", "since", "days", "researchers":
        [{"date", "ids"}]}: profile ids only (names and units come from
        researchers.json). New calls are read from the same state by
        export_funding.py and go into the encrypted funding index.

A researcher is new when none of their keys was seen before: the profile id, the
work e-mail and the Cristin id. So an NVA-only profile ("nva-<id>") that becomes a
Scopus profile, or a Scopus id that changes, is not reported as a new person.
Someone who is missing for a week (a collector outage) and comes back is not new
either: keys are never forgotten.

The first run records everything as the baseline. Calls are then seeded from
config.CALLS_HISTORY (the date build_calls.py first saw each call), so calls found
since the first funding run show at once; researchers start from this run. Each
funding source has its own baseline (its first date), so adding a new funder does
not list all of its calls as new.
"""
import json
import re
from datetime import date, datetime, timedelta

import config
from fsutil import write_text

OUT = config.PUBLIC / "changes.json"


def researcher_keys(r: dict) -> list[str]:
    keys = [f"id:{r['scopus_id']}"]
    if r.get("email"):
        keys.append(f"email:{r['email'].strip().lower()}")
    m = re.search(r"/research-profile/(\d+)", (r.get("links") or {}).get("nva", ""))
    nva = m.group(1) if m else (r["scopus_id"][4:] if r["scopus_id"].startswith("nva-") else None)
    if nva:
        keys.append(f"cristin:{nva}")
    return keys


def seed_calls(history: dict) -> dict[str, str]:
    """Call id -> date of its first "new" entry in calls_history.json."""
    out = {}
    for cid, changes in history.items():
        dates = [c["date"][:10] for c in changes if c.get("field") == "new"]
        if dates:
            out[cid] = min(dates)
    return out


def update(state: dict, researchers: list[dict], calls: list[tuple[str, str]], today: str,
           history: dict | None = None) -> dict[str, str]:
    """Records today's researchers and (call id, source) pairs in state; returns
    profile id -> first-seen date. Each funding source has its own baseline: the
    calls of a source seen in its first run (the first run of this stage, or the week
    a new funder was added) are not "new"."""
    if not state:
        state.update(baseline={"researchers": today, "calls": {}}, researchers={},
                     calls=seed_calls(history or {}))
    seen_r, seen_c, base_c = state["researchers"], state["calls"], state["baseline"]["calls"]
    first = {}
    for r in researchers:
        keys = researcher_keys(r)
        known = [seen_r[k] for k in keys if k in seen_r]
        d = min(known) if known else today
        for k in keys:
            seen_r.setdefault(k, d)
        first[r["scopus_id"]] = d
    for cid, source in calls:
        d = seen_c.setdefault(cid, today)
        base_c[source] = min(base_c.get(source, d), d)
    state["call_source"] = state.get("call_source", {}) | dict(calls)
    return first


def recent(first: dict[str, str], baseline: str, today: str, days: int = config.CHANGES_DAYS) -> list[dict]:
    """[{"date", "ids"}], newest first: items first seen after the baseline, within `days`."""
    since = (date.fromisoformat(today) - timedelta(days=days)).isoformat()
    by_date: dict[str, list[str]] = {}
    for item, d in first.items():
        if d > baseline and d > since:
            by_date.setdefault(d, []).append(item)
    return [{"date": d, "ids": sorted(by_date[d])} for d in sorted(by_date, reverse=True)]


def new_calls(state: dict, open_ids: set[str], today: str) -> list[dict]:
    """For export_funding.py: open or planned calls first seen within config.CHANGES_DAYS,
    after their source's baseline."""
    if not state:
        return []
    base, source = state["baseline"]["calls"], state.get("call_source", {})
    first = {c: d for c, d in state["calls"].items()
             if c in open_ids and c in source and d > base.get(source[c], d)}
    return recent(first, "", today)


def load_state() -> dict:
    try:
        return json.loads(config.FIRST_SEEN.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def main() -> None:
    today = datetime.now().date().isoformat()
    researchers = json.loads((config.PUBLIC / "researchers.json").read_text(encoding="utf-8"))
    calls = json.loads(config.CALLS.read_text(encoding="utf-8"))["calls"] if config.CALLS.exists() else []
    history = (json.loads(config.CALLS_HISTORY.read_text(encoding="utf-8"))
               if config.CALLS_HISTORY.exists() else {})
    state = load_state()
    first_run = not state
    first = update(state, researchers, [(c["id"], c["source"]) for c in calls], today, history)
    write_text(config.FIRST_SEEN, json.dumps(state, ensure_ascii=False, indent=1))
    weeks = recent(first, state["baseline"]["researchers"], today)
    write_text(OUT, json.dumps({"generated": today, "since": state["baseline"]["researchers"],
                                "days": config.CHANGES_DAYS, "researchers": weeks},
                               ensure_ascii=False, separators=(",", ":")))
    open_ids = {c["id"] for c in calls if c["fields"]["status"]["v"] != "closed"}
    n_calls = sum(len(w["ids"]) for w in new_calls(state, open_ids, today))
    print(("Baseline recorded (first run): nothing is reported as new yet. " if first_run else "")
          + f"New in the last {config.CHANGES_DAYS} days: {sum(len(w['ids']) for w in weeks)} researchers, "
          f"{n_calls} open/planned calls -> {OUT.name}")


if __name__ == "__main__":
    main()
