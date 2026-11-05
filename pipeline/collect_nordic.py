#!/usr/bin/env python3
"""
Stage 1g – Collect funding calls from Nordic funders (any network, no key).

Input:  NordForsk's website API (config.NORDFORSK_API, Drupal JSON:API: every
        "call" record with its topics and programme) and Nordic Energy Research's
        website API (config.NER_API, WordPress: every "funding" record plus the
        status, type and topic names)
Output: config.RAW_NORDIC/
          nordforsk.json     {"fetched", "calls": [...], "included": {id: record}}
          nordicenergy.json  {"fetched", "items": [...], "terms": {taxonomy: {id: name}}}
          sync_status.json   per source: last attempt, last success, errors

Both sources hold well under a hundred records, so everything is fetched on every
run (a handful of requests, one per config.NORDIC_SLEEP seconds). Which calls are
shown is decided later (nordic.py). If a site cannot be reached, its previous file
stays untouched and the error is recorded, so the website keeps the last verified data.

Usage:
  python pipeline/collect_nordic.py
"""
import json
import time
from datetime import datetime

import requests

import config

STATUS = config.RAW_NORDIC / "sync_status.json"
NER_TAXONOMIES = ("current_status", "funding_type", "topics")


class Fetcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = config.USER_AGENT
        self.last = 0.0

    def get(self, url: str) -> requests.Response:
        for attempt in range(3):
            wait = config.NORDIC_SLEEP - (time.monotonic() - self.last)
            if wait > 0:
                time.sleep(wait)
            self.last = time.monotonic()
            try:
                r = self.session.get(url, timeout=60)
                if r.status_code == 200:
                    return r
                if r.status_code in (401, 403, 404, 410):
                    raise RuntimeError(f"{r.status_code} for {url}")
            except requests.RequestException:
                if attempt == 2:
                    raise
            time.sleep(5 * (attempt + 1))
        raise RuntimeError(f"Could not fetch {url}")


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def nordforsk(fetch: Fetcher) -> dict:
    url = f"{config.NORDFORSK_API}?page[limit]=50&sort=-created&include=field_topic,field_program"
    calls, included = [], {}
    while url:
        doc = fetch.get(url).json()
        calls += doc["data"]
        for x in doc.get("included", []):
            included[x["id"]] = x
        url = (doc.get("links", {}).get("next") or {}).get("href")
    if not calls:
        raise RuntimeError("no calls returned")
    return {"fetched": now(), "source_url": config.NORDFORSK_API, "calls": calls, "included": included}


def ner_all(fetch: Fetcher, path: str) -> list[dict]:
    out, page = [], 1
    while True:
        r = fetch.get(f"{config.NER_API}{path}{'&' if '?' in path else '?'}per_page=100&page={page}")
        out += r.json()
        if page >= int(r.headers.get("X-WP-TotalPages", 1)):
            return out
        page += 1


def nordicenergy(fetch: Fetcher) -> dict:
    terms = {tax: {str(t["id"]): t["name"] for t in ner_all(fetch, tax)} for tax in NER_TAXONOMIES}
    items = ner_all(fetch, "funding")
    if not items:
        raise RuntimeError("no funding items returned")
    return {"fetched": now(), "source_url": config.NER_API + "funding", "items": items, "terms": terms}


SOURCES = {"nordforsk": nordforsk, "nordicenergy": nordicenergy}


def main() -> None:
    config.RAW_NORDIC.mkdir(parents=True, exist_ok=True)
    status = json.loads(STATUS.read_text(encoding="utf-8")) if STATUS.exists() else {}
    fetch = Fetcher()
    for name, collect in SOURCES.items():
        st = status.setdefault(name, {})
        st.update({"last_attempt": now(), "errors": []})
        try:
            doc = collect(fetch)
        except Exception as e:  # keep the last good data, record the problem
            st["errors"].append({"url": config.NORDFORSK_API if name == "nordforsk" else config.NER_API,
                                 "error": str(e)})
            print(f"{name}: {e} (keeping previous data)")
            continue
        (config.RAW_NORDIC / f"{name}.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        st["last_success"] = now()
        print(f"{name}: {len(doc.get('calls') or doc.get('items'))} records")
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
