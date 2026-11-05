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

The work e-mail is only on each person's profile page: it is read once per person
in the atlas departments and kept in config.DIRECTORY_EMAILS, so later runs only
read the pages of new staff.

Polite: about 80 small requests (plus one per new person for the e-mail), one per
DIRECTORY_SLEEP seconds. Works from any network. Run it again before each pipeline
refresh.
"""
import html
import json
import math
import re
import sys
import time
import unicodedata
from datetime import datetime

import requests

import config
import fsutil
import runlock

PAGE_SIZE = config.DIRECTORY_PAGE_SIZE
LANGS = {"nb": "sok/ansatte", "en": "search/employees"}
FACET = re.compile(r'href="[^"]*employees%5B\d%5D=department%3A(\d+)[^"]*"[^>]*>(.*?)</a>', re.S)
CARD = re.compile(r'<a href="(/(?:nb|en)/profile/[^"]+)"[^>]*class="profile_search_card__link".*?'
                  r'profile_search_card__name">(.*?)</div>\s*'
                  r'(?:<div class="profile_search_card__position">(.*?)</div>)?', re.S)
MAILTO = re.compile(r'href="mailto:([^"?]+)')
GENERIC_EMAILS = {"post@uis.no"}   # site-wide addresses, never a person's


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
    return fetch_url(s, config.DIRECTORY_URL.format(lang=lang, path=LANGS[lang]), params)


def retry_after(r: requests.Response, default: float) -> float:
    """Seconds to wait before a retry: a numeric Retry-After header (capped), else default."""
    value = (r.headers.get("Retry-After") or "").strip()
    return min(float(value), config.MAX_RETRY_AFTER) if value.isdigit() else default


def fetch_url(s: requests.Session, url: str, params: dict | None = None) -> str:
    attempts = 5
    for attempt in range(attempts):
        last = attempt == attempts - 1   # no wait after the final attempt
        try:
            r = s.get(url, params=params, timeout=60)
        except requests.RequestException as exc:
            print(f"  network problem ({exc}); retrying…")
            if not last:
                time.sleep(2 ** attempt * 3)
            continue
        time.sleep(config.DIRECTORY_SLEEP)
        if r.status_code == 200:
            return r.text
        if r.status_code >= 500 or r.status_code == 429:
            if not last:
                time.sleep(retry_after(r, 2 ** attempt * 3) if r.status_code == 429 else 2 ** attempt * 3)
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


def ascii_fold(s: str) -> str:
    """Lower-case ASCII form of a name, as used in e-mail addresses (Ø -> o, Æ -> ae)."""
    s = s.lower().replace("ø", "o").replace("æ", "ae").replace("å", "a")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def email_of(page: str, name: str | None = None) -> str | None:
    """The person's work e-mail from their profile page. With several mailto links
    (a unit's or a project's address next to the person's), the one whose local part
    contains a part of the person's name wins; otherwise the first non-generic one."""
    addresses = []
    for address in MAILTO.findall(page):
        address = html.unescape(address).strip().lower()
        if address and address not in GENERIC_EMAILS and address not in addresses:
            addresses.append(address)
    if not addresses:
        return None
    tokens = [t for t in re.split(r"[^a-z]+", ascii_fold(name or "")) if len(t) >= 3]
    for address in addresses:
        local = address.split("@", 1)[0]
        if any(t in local for t in tokens):
            return address
    return addresses[0]


def add_emails(s: requests.Session, people: dict[str, dict]) -> None:
    """Work e-mail of everyone in the atlas departments, read from their profile page.
    The listing does not show it, so each new person costs one request; known addresses
    come from config.DIRECTORY_EMAILS (local only) and are not fetched again."""
    cache = (json.loads(config.DIRECTORY_EMAILS.read_text(encoding="utf-8"))
             if config.DIRECTORY_EMAILS.exists() else {})
    wanted = [url for url, p in people.items()
              if any(int(u) in config.DIRECTORY_DEPARTMENTS for u in p["units"])]
    new = [url for url in wanted if url not in cache]
    print(f"E-mail addresses: {len(wanted) - len(new)} known, {len(new)} profile pages to read…")
    for i, url in enumerate(new, 1):
        try:
            cache[url] = email_of(fetch_url(s, url), people[url]["name"])
        except (requests.RequestException, RuntimeError) as exc:
            print(f"  could not read {url}: {exc}")
            continue
        if i % 100 == 0:
            print(f"  {i}/{len(new)}")
            fsutil.write_json(config.DIRECTORY_EMAILS, cache, indent=1)
    # Forget people who left. Only called after a complete listing (see main), so a
    # short run never empties the cache.
    cache = {url: cache[url] for url in wanted if url in cache}
    fsutil.write_json(config.DIRECTORY_EMAILS, cache, indent=1)
    for url in wanted:
        if cache.get(url):
            people[url]["email"] = cache[url]


def listing_complete(parsed: int, listed: int) -> bool:
    """True if the cards parsed from the unit pages cover enough of the people the
    facets report; otherwise the page layout probably changed."""
    return parsed > 0 and parsed >= config.DIRECTORY_MIN_PARSED_SHARE * listed


def main() -> None:
    if not runlock.acquire():
        sys.exit("Another pipeline run is in progress (run_weekly.py or run_all.py): not started.")
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
    listed = parsed = 0
    for i, uid in enumerate(leaves, 1):
        u = units[uid]
        print(f"  [{i}/{len(leaves)}] {u['nb']} ({u['count']})")
        nb = members(s, "nb", uid, u["count"])
        listed += u["count"]
        parsed += len(nb)
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

    if not listing_complete(parsed, listed):
        print(f"\nStopped: the unit facets list {listed} people, but only {parsed} could be read from the "
              f"listing pages (the page layout may have changed). Nothing was written; "
              f"the previous directory and e-mail cache are kept.")
        sys.exit(1)

    config.RAW_DIRECTORY.mkdir(parents=True, exist_ok=True)
    add_emails(s, people)
    out = {"generated": datetime.now().isoformat(timespec="seconds"),
           "units": units, "employees": list(people.values())}
    fsutil.write_json(config.DIRECTORY, out, indent=1)
    in_scope = sum(1 for p in people.values()
                   if any(int(u) in config.DIRECTORY_DEPARTMENTS for u in p["units"]))
    print(f"\nDone. {len(people)} employees, {in_scope} in the atlas departments.")
    print(f"Output (personal data, local only, never commit): {config.DIRECTORY}")


if __name__ == "__main__":
    main()
