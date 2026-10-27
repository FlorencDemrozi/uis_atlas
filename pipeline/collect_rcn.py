#!/usr/bin/env python3
"""
Stage 1c – Collect funding calls from the Research Council of Norway (any network).

Input:  the call lists in config.RCN_LISTS: current calls in Norwegian
        (/utlysninger/) and English (/en/call-for-proposals/), plus completed calls
Output: config.RAW_RCN/
          list_<n>.json           the call lists as published (n = position in RCN_LISTS)
          calls/<id>.json         one file per call: listing entry + Norwegian and
                                  English page data, with fetch time
          sync_status.json        last attempt, last success, errors

The site embeds each page's content as JSON; we store that JSON (see rcn.py).
Polite: one request per config.RCN_SLEEP seconds, ~2 requests per call.
Completed calls are fetched once and then kept; current calls are refreshed on
every run. If the site cannot be reached, the previous files stay untouched and
the error is recorded, so the website keeps showing the last verified data.

Usage:
  python pipeline/collect_rcn.py          # refresh current calls, add new ones
  python pipeline/collect_rcn.py --full   # also refetch completed calls
"""
import argparse
import json
import time
from datetime import datetime

import requests

import config
import rcn

CALLS_DIR = config.RAW_RCN / "calls"
STATUS = config.RAW_RCN / "sync_status.json"


class Fetcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = config.USER_AGENT
        self.last = 0.0

    def get(self, url: str) -> str:
        for attempt in range(3):
            wait = config.RCN_SLEEP - (time.monotonic() - self.last)
            if wait > 0:
                time.sleep(wait)
            self.last = time.monotonic()
            try:
                r = self.session.get(url, timeout=60)
                if r.status_code == 200:
                    r.encoding = "utf-8"
                    return r.text
                if r.status_code in (404, 410):
                    raise RuntimeError(f"{r.status_code} for {url}")
            except requests.RequestException:
                if attempt == 2:
                    raise
            time.sleep(5 * (attempt + 1))
        raise RuntimeError(f"Could not fetch {url}")


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def list_entries(props: dict, timeframe: str) -> list[dict]:
    out = []
    for group in props.get("groups", []):
        for p in group.get("proposals", []):
            out.append({
                "id": str(p["id"]), "title": rcn.clean(p.get("title")), "url": rcn.absolute(p["url"]),
                "group": rcn.clean(group.get("title")), "date": rcn.clean(p.get("date")),
                "year": p.get("year"), "status": rcn.clean((p.get("status") or {}).get("text")),
                "metadata": {rcn.clean(m.get("label")): rcn.clean(m.get("text"))
                             for m in (p.get("metadata") or {}).get("items", [])},
                "tags": (p.get("tags") or {}).get("list", []),
                "text": rcn.clean(p.get("text")), "international": bool(p.get("isInternational")),
                "timeframe": timeframe,
            })
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--full", action="store_true", help="refetch completed calls too")
    args = ap.parse_args()

    CALLS_DIR.mkdir(parents=True, exist_ok=True)
    status = json.loads(STATUS.read_text(encoding="utf-8")) if STATUS.exists() else {}
    status.update({"last_attempt": now(), "errors": []})
    fetch = Fetcher()

    entries: dict[str, dict] = {}
    for n, (url, timeframe) in enumerate(config.RCN_LISTS):
        try:
            props = rcn.react_props(fetch.get(url), "ProposalListPage")
            if not props:
                raise RuntimeError("call list format not recognised")
        except Exception as e:  # keep the last good data, record the problem
            status["errors"].append({"url": url, "error": str(e)})
            print(f"List {url}: {e}")
            continue
        (config.RAW_RCN / f"list_{n}.json").write_text(
            json.dumps({"fetched": now(), "url": url, "props": props}, ensure_ascii=False), encoding="utf-8")
        found = list_entries(props, timeframe)
        print(f"List {url}: {len(found)} calls")
        # First list wins: a call on the Norwegian and the English list keeps its
        # Norwegian entry; a call on a current and the completed list counts as current.
        for e in found:
            entries.setdefault(e["id"], e)
    print(f"Lists: {len(entries)} calls")

    fetched = kept = 0
    for i, (cid, entry) in enumerate(sorted(entries.items()), 1):
        path = CALLS_DIR / f"{cid}.json"
        old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        if (old and not args.full and entry["timeframe"] == "completed"
                and old["listing"]["timeframe"] == "completed"):
            old["listing"] = entry
            path.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
            kept += 1
            continue
        try:
            page = fetch.get(entry["url"])
            nb = rcn.react_props(page, "ProposalPage")
            if not nb:
                raise RuntimeError("call page format not recognised")
            en_url, en = rcn.english_url(page), None
            if en_url:
                try:
                    en = rcn.react_props(fetch.get(en_url), "ProposalPage")
                except Exception as e:
                    status["errors"].append({"url": en_url, "error": str(e)})
        except Exception as e:
            status["errors"].append({"url": entry["url"], "error": str(e)})
            print(f"  [{i}/{len(entries)}] {entry['title']}: {e} (keeping previous data)")
            continue
        path.write_text(json.dumps({"id": cid, "listing": entry, "url": entry["url"], "en_url": en_url,
                                    "fetched": now(), "nb": nb, "en": en}, ensure_ascii=False),
                        encoding="utf-8")
        fetched += 1
        print(f"  [{i}/{len(entries)}] {entry['title']}")

    if entries:
        status["last_success"] = now()
        status["calls_listed"] = sorted(entries)
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Calls: {fetched} fetched, {kept} completed calls kept, {len(status['errors'])} errors.")


if __name__ == "__main__":
    main()
