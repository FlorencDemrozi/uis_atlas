#!/usr/bin/env python3
"""
Stage 2b – Is a researcher's UiS affiliation still active? (Cristin person records)

Input:  config.CRISTIN_CANDIDATES (written by build_profiles.py: Cristin ids of people
        with recent work whom the UiS employee directory does not confirm)
Output: config.RAW_CRISTIN (local only, never commit)

The public employee directory leaves out some current staff, and people who have left
stay in the atlas for a while through their recent UiS papers. Cristin (read through
the open NVA API, any network) marks each affiliation as active or not, so
build_profiles.py can tell current staff ("current"), people whose UiS affiliations
have all ended ("former"), and the rest ("unknown").

Only each person's UiS affiliations are kept: unit id, active, role title (nb/en).
Records are read again after config.CRISTIN_REFRESH_DAYS. A network problem is
reported but does not stop the pipeline: the cached records are kept.

run_all.py runs build_profiles.py, this script, and build_profiles.py again.
"""
import json
import sys
import time
from datetime import date, datetime, timedelta

import requests

import config
from fsutil import write_text


def uis_affiliations(record: dict) -> list[dict]:
    """The UiS affiliations of one Cristin person record (open NVA API format)."""
    out = []
    for a in record.get("affiliations") or []:
        unit = (a.get("organization") or "").rstrip("/").rsplit("/", 1)[-1]
        if unit.split(".")[0] != config.CRISTIN_UIS:
            continue
        labels = (a.get("role") or {}).get("labels") or {}
        out.append({"unit": unit, "active": bool(a.get("active")),
                    "nb": labels.get("nb"), "en": labels.get("en")})
    return out


def fetch(s: requests.Session, cid: str) -> dict | None:
    """The person's record, {} if Cristin does not know the id, None on a network problem."""
    for attempt in range(3):
        try:
            r = s.get(config.CRISTIN_PERSON_URL.format(cid), timeout=60)
        except requests.RequestException:
            time.sleep(3 * (attempt + 1))
            continue
        time.sleep(config.CRISTIN_SLEEP)
        if r.status_code == 200:
            return r.json()
        if r.status_code == 404:
            return {}
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(3 * (attempt + 1))
            continue
        return None
    return None


def main() -> None:
    if not config.CRISTIN_CANDIDATES.exists():
        sys.exit("No candidates yet: run pipeline/build_profiles.py first.")
    candidates = json.loads(config.CRISTIN_CANDIDATES.read_text(encoding="utf-8"))
    cache = (json.loads(config.RAW_CRISTIN.read_text(encoding="utf-8"))
             if config.RAW_CRISTIN.exists() else {"persons": {}})
    persons = cache["persons"]
    stale = (date.today() - timedelta(days=config.CRISTIN_REFRESH_DAYS)).isoformat()
    todo = [c for c in candidates if c not in persons or persons[c]["checked"] < stale]
    print(f"Cristin: {len(candidates)} people to check, {len(todo)} to read "
          f"({len(candidates) - len(todo)} recent records cached).")

    config.RAW_CRISTIN.parent.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    s.headers["User-Agent"] = config.USER_AGENT
    failed = 0
    for i, cid in enumerate(todo, 1):
        record = fetch(s, cid)
        if record is None:
            failed += 1
            if failed >= 10 and failed == i:   # nothing works: stop early, keep the cache
                print("  Cristin does not answer; keeping the cached records.")
                break
            continue
        persons[cid] = {"checked": date.today().isoformat(), "uis": uis_affiliations(record)}
        if i % 100 == 0:
            print(f"  {i}/{len(todo)}")
            cache["generated"] = datetime.now().isoformat(timespec="seconds")
            write_text(config.RAW_CRISTIN, json.dumps(cache, ensure_ascii=False))
    cache["generated"] = datetime.now().isoformat(timespec="seconds")
    write_text(config.RAW_CRISTIN, json.dumps(cache, ensure_ascii=False))
    known = [persons[c] for c in candidates if c in persons]
    active = sum(1 for p in known if any(a["active"] for a in p["uis"]))
    ended = sum(1 for p in known if p["uis"] and not any(a["active"] for a in p["uis"]))
    print(f"Done ({failed} failed): {active} with an active UiS affiliation, {ended} with ended "
          f"UiS affiliations only, {len(known) - active - ended} without UiS affiliations.")


if __name__ == "__main__":
    main()
