#!/usr/bin/env python3
"""
Stage 1b – Collect current staff from the public UiS employee directory.

Input:  www.uis.no/nb/sok/ansatte and www.uis.no/en/search/employees
Output: config.DIRECTORY (personal data: local only, never commit)

The directory is the source of truth for who works at UiS today and in which
unit. build_profiles.py matches Scopus authors to it by name: a match confirms
the person as current staff, gives today's department, position and UiS
profile link.

How the site works (checked 2026-10-23): the list is server-rendered and can be
filtered by unit with ?employees[0]=department:<id>. Facets list the top-level
units (faculties, museum, divisions) and, once a unit is selected, its
sub-units (departments, centres, administration). "Load more" pages are
cumulative: page=N returns the first (N+1)×14 people.

Polite: about 80 small requests, one per DIRECTORY_SLEEP seconds. Works from any
network. Run it again before each pipeline refresh.
"""
import html
import json
import math
import re
import sys
import time
from datetime import datetime

import requests

import config

PAGE_SIZE = 14
LANGS = {"nb": "sok/ansatte", "en": "search/employees"}
FACET = re.compile(r'href="[^"]*employees%5B\d%5D=department%3A(\d+)[^"]*"[^>]*>(.*?)</a>', re.S)
CARD = re.compile(r'<a href="(/(?:nb|en)/profile/[^"]+)"[^>]*class="profile_search_card__link".*?'
                  r'profile_search_card__name">(.*?)</div>\s*'
                  r'(?:<div class="profile_search_card__position">(.*?)</div>)?', re.S)


def text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment or ""))).strip()


def clean_position(p: str) -> str | None:
    return text(p).rstrip("# ").strip() or None


def fetch(s: requests.Session, lang: str, unit: str | None = None, page: int = 0) -> str:
    params = {}
    if unit:
        params["employees[0]"] = f"department:{unit}"
    if page:
        params["page"] = page
    url = config.DIRECTORY_URL.format(lang=lang, path=LANGS[lang])
    for attempt in range(5):
        try:
            r = s.get(url, params=params, timeout=60)
        except requests.RequestException as exc:
            print(f"  network problem ({exc}); retrying…")
            time.sleep(2 ** attempt * 3)
            continue
        time.sleep(config.DIRECTORY_SLEEP)
        if r.status_code == 200:
            return r.text
        if r.status_code >= 500 or r.status_code == 429:
            time.sleep(2 ** attempt * 3)
            continue
        r.raise_for_status()
    raise RuntimeError(f"Gave up on {url} {params}")


def facets(page: str) -> dict[str, tuple[str, int]]:
    """Unit id -> (label, number of people), from the facet links on a page."""
    out = {}
    for uid, label in FACET.findall(page):
        m = re.match(r"(.*)\((\d+)\)$", text(label))
        if m:
            out[uid] = (m.group(1).strip(), int(m.group(2)))
    return out


def members(s: requests.Session, lang: str, unit: str, count: int) -> list[dict]:
    page = fetch(s, lang, unit, max(0, math.ceil(count / PAGE_SIZE) - 1))
    out = [{"url": "https://www.uis.no" + href, "name": text(name), "position": clean_position(pos)}
           for href, name, pos in CARD.findall(page)]
    if len(out) < count:
        print(f"  warning: unit {unit} ({lang}) lists {count} people, got {len(out)}")
    return out


def main() -> None:
    s = requests.Session()
    s.headers["User-Agent"] = "UiS Researcher Atlas (research directory prototype; contact via uis.no)"

    print("Reading the unit structure…")
    top = facets(fetch(s, "nb"))
    if not top:
        sys.exit("No units found – the directory page layout may have changed.")
    units = {}
    for uid, (label, count) in top.items():
        units[uid] = {"nb": label, "parent": None, "count": count}
        for sub, (sub_label, sub_count) in facets(fetch(s, "nb", uid)).items():
            if sub not in top:
                units[sub] = {"nb": sub_label, "parent": uid, "count": sub_count}
    for uid, (label, _) in facets(fetch(s, "en")).items():
        if uid in units:
            units[uid]["en"] = label
    leaves = [u for u in units if not any(v["parent"] == u for v in units.values())]
    print(f"  {len(top)} top-level units, {len(units) - len(top)} sub-units, {len(leaves)} to list")

    missing = [uid for uid in config.DIRECTORY_DEPARTMENTS if str(uid) not in units]
    if missing:
        print(f"  warning: directory units in config.py not found on the site: {missing}")

    people: dict[str, dict] = {}   # keyed by Norwegian profile URL
    for i, uid in enumerate(leaves, 1):
        u = units[uid]
        print(f"  [{i}/{len(leaves)}] {u['nb']} ({u['count']})")
        nb = members(s, "nb", uid, u["count"])
        en = {m["name"]: m for m in members(s, "en", uid, u["count"])}
        for m in nb:
            p = people.setdefault(m["url"], {"name": m["name"], "url_nb": m["url"], "units": [],
                                             "position_nb": m["position"]})
            if uid not in p["units"]:
                p["units"].append(uid)
            e = en.get(m["name"])
            if e:
                p.setdefault("url_en", e["url"])
                p.setdefault("position_en", e["position"])

    config.RAW_DIRECTORY.mkdir(parents=True, exist_ok=True)
    out = {"generated": datetime.now().isoformat(timespec="seconds"),
           "units": units, "employees": list(people.values())}
    config.DIRECTORY.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    in_scope = sum(1 for p in people.values()
                   if any(int(u) in config.DIRECTORY_DEPARTMENTS for u in p["units"]))
    print(f"\nDone. {len(people)} employees, {in_scope} in the atlas departments.")
    print(f"Output (personal data, local only, never commit): {config.DIRECTORY}")


if __name__ == "__main__":
    main()
