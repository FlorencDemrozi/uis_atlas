#!/usr/bin/env python3
"""
Stage 1d – Collect EU funding topics from the European Commission's Funding &
Tenders Portal (any network, no key).

Input:  the portal's public search API (config.EU_SEARCH_URL) for the topic list,
        and its per-topic JSON (config.EU_TOPIC_URL) for the full text
Output: config.RAW_EU/
          list.json               every listed topic as returned by the search API
          topics/<ID>.json        one file per topic: listing entry + topic details
          sync_status.json        last attempt, last success, errors

The matching works on topics (Programme → Work programme → Call → Topic), so the
unit collected here is the topic, keyed by its official identifier.
Listed: open and forthcoming topics of every programme (calls for proposals and
cascade calls), plus topics closed within config.EU_CLOSED_MONTHS for history.

Incremental: a topic's details are fetched again only when the search index
reports a new checksum or status, or when they are older than
config.EU_DETAIL_MAX_AGE_DAYS. Closed topics are fetched once. One request per
config.EU_SLEEP seconds. If the portal cannot be reached, the previous files stay
and the error is recorded, so the website keeps the last verified data.

Usage:
  python pipeline/collect_eu.py           # incremental
  python pipeline/collect_eu.py --full    # refetch every topic's details
"""
import argparse
import json
import re
import time
from datetime import date, datetime, timedelta

import requests

import config

TOPICS_DIR = config.RAW_EU / "topics"
STATUS = config.RAW_EU / "sync_status.json"
PAGE = 100


class Portal:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = config.USER_AGENT
        self.last = 0.0

    def _wait(self):
        wait = config.EU_SLEEP - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.monotonic()

    def request(self, method: str, url: str, **kw) -> requests.Response:
        for attempt in range(4):
            self._wait()
            try:
                r = self.session.request(method, url, timeout=120, **kw)
                if r.status_code == 200:
                    return r
                if r.status_code in (404, 410):
                    raise LookupError(f"{r.status_code} for {url}")
            except requests.RequestException:
                if attempt == 3:
                    raise
            time.sleep(5 * (attempt + 1))
        raise RuntimeError(f"Could not fetch {url}")

    def search(self, query: dict, sort: list[dict], page: int) -> dict:
        part = lambda v: (None, json.dumps(v), "application/json")
        r = self.request("POST", config.EU_SEARCH_URL,
                         params={"apiKey": "SEDIA", "text": "***", "pageSize": PAGE, "pageNumber": page},
                         files={"query": part(query), "languages": part(["en"]), "sort": part(sort)})
        return r.json()

    def topic(self, identifier: str) -> dict:
        r = self.request("GET", config.EU_TOPIC_URL.format(identifier.lower()))
        r.encoding = "utf-8"
        return r.json().get("TopicDetails") or {}


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def first(meta: dict, key: str):
    v = meta.get(key)
    return v[0] if isinstance(v, list) and v else v


def listing_entry(result: dict) -> dict | None:
    m = result.get("metadata") or {}
    ident = first(m, "identifier")
    if not ident:
        return None
    return {
        "identifier": ident, "type": first(m, "type"),
        "status": config.EU_STATUS.get(str(first(m, "status")), "unknown"),
        # A topic with several cut-offs lists them all; the last one decides when it ends.
        "checksum": first(m, "esST_checksum"), "deadline": max(m.get("deadlineDate") or [""]) or None,
        "programme_id": first(m, "frameworkProgramme"), "call_identifier": first(m, "callIdentifier"),
        "title": first(m, "title"), "url": result.get("url"), "metadata": m,
    }


def file_name(identifier: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", identifier) + ".json"


def list_topics(portal: Portal) -> dict[str, dict]:
    """Open and forthcoming topics, then closed ones newest deadline first until the cutoff.
    Pages are sorted on a unique key (identifier last): with ties the index returns
    some records on two pages and skips others."""
    out: dict[str, dict] = {}
    open_q = {"bool": {"must": [{"terms": {"type": config.EU_TYPES}},
                                {"terms": {"status": ["31094501", "31094502"]}}]}}
    page = 1
    while True:
        d = portal.search(open_q, [{"field": "identifier", "order": "ASC"}], page)
        for res in d.get("results", []):
            e = listing_entry(res)
            if e:
                out.setdefault(e["identifier"], e)
        print(f"  open/forthcoming: page {page}, {len(out)} of {d.get('totalResults')}")
        if page * PAGE >= int(d.get("totalResults") or 0) or not d.get("results"):
            break
        page += 1

    cutoff = (date.today() - timedelta(days=round(30.5 * config.EU_CLOSED_MONTHS))).isoformat()
    closed_q = {"bool": {"must": [{"terms": {"type": config.EU_TYPES}}, {"terms": {"status": ["31094503"]}}]}}
    page, n_closed = 1, 0
    while True:
        d = portal.search(closed_q, [{"field": "deadlineDate", "order": "DESC"},
                                     {"field": "identifier", "order": "ASC"}], page)
        results = d.get("results", [])
        done = not results
        for res in results:
            e = listing_entry(res)
            if not e:
                continue
            if e["deadline"] and e["deadline"][:10] < cutoff:
                done = True
                break
            if e["identifier"] not in out:
                out[e["identifier"]] = e
                n_closed += 1
        print(f"  closed since {cutoff}: page {page}, {n_closed} topics")
        if done or page * PAGE >= int(d.get("totalResults") or 0):
            break
        page += 1
    return out


def needs_fetch(entry: dict, old: dict | None, full: bool) -> bool:
    if full or old is None or not old.get("details"):
        return True
    prev = old["listing"]
    if entry["status"] == "closed" and prev["status"] == "closed":
        return False
    if entry["checksum"] != prev.get("checksum") or entry["status"] != prev["status"]:
        return True
    age = datetime.now() - datetime.fromisoformat(old["fetched"])
    return age > timedelta(days=config.EU_DETAIL_MAX_AGE_DAYS)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--full", action="store_true", help="refetch every topic's details")
    args = ap.parse_args()

    TOPICS_DIR.mkdir(parents=True, exist_ok=True)
    status = json.loads(STATUS.read_text(encoding="utf-8")) if STATUS.exists() else {}
    status.update({"last_attempt": now(), "errors": []})
    portal = Portal()

    try:
        entries = list_topics(portal)
    except Exception as e:  # keep the last good data, record the problem
        status["errors"].append({"url": config.EU_SEARCH_URL, "error": str(e)})
        STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
        raise SystemExit(f"EU topic list could not be read: {e} (previous data kept)")
    (config.RAW_EU / "list.json").write_text(json.dumps({"fetched": now(), "topics": list(entries.values())},
                                                        ensure_ascii=False), encoding="utf-8")
    print(f"Listed: {len(entries)} topics")

    fetched = kept = 0
    for i, (ident, entry) in enumerate(sorted(entries.items()), 1):
        path = TOPICS_DIR / file_name(ident)
        old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        if not needs_fetch(entry, old, args.full):
            old["listing"] = entry
            path.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
            kept += 1
            continue
        details = None
        if entry["type"] == "1":   # cascade calls (type 2) have no topic page: the listing is the record
            try:
                details = portal.topic(ident)
            except Exception as e:
                status["errors"].append({"url": config.EU_TOPIC_URL.format(ident.lower()), "error": str(e)})
                print(f"  [{i}/{len(entries)}] {ident}: {e} (keeping previous data)")
                # Keep the previous details; without any, the listing (which carries
                # the topic text too) is the record until the page can be read.
                record = old or {"id": ident, "fetched": now(), "details": None}
                record["listing"] = entry
                path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
                continue
        path.write_text(json.dumps({"id": ident, "listing": entry, "fetched": now(), "details": details},
                                   ensure_ascii=False), encoding="utf-8")
        fetched += 1
        if fetched % 50 == 0:
            print(f"  [{i}/{len(entries)}] {fetched} topic pages fetched")

    status["last_success"] = now()
    status["topics_listed"] = sorted(entries)
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Topics: {fetched} fetched, {kept} unchanged, {len(status['errors'])} errors.")


if __name__ == "__main__":
    main()
