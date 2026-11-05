#!/usr/bin/env python3
"""
Stage 1f – Collect UiS research output from NVA (Nasjonalt vitenarkiv, Sikt).

Input:  NVA's open search API (config.NVA_SEARCH_URL), any network, no key
Output: config.RAW_NVA/
          <year>.jsonl     one trimmed record per output (see nva.trim)
          state.json       finished years and when they were fetched

Everything registered with a UiS unit (sub-units included) and published since
config.FIRST_YEAR, except student theses (config.NVA_SKIPPED_TYPES). Only UiS
contributors with a Cristin person id are kept.

Resumable by year: a year is written in one go when all its pages are in. Once a
year is finished it is fetched again only while it is among the last
config.NVA_REFRESH_YEARS years (late registrations). One request per
config.NVA_SLEEP seconds.

Usage:
  python pipeline/collect_nva.py           # missing and recent years
  python pipeline/collect_nva.py --full    # every year again
"""
import argparse
import json
import sys
import time
from datetime import datetime

import requests

import config
import fsutil
import runlock
from nva import trim


class Api:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": config.USER_AGENT, "Accept": "application/json"})
        self.last = 0.0

    def get(self, url: str, params: dict | None = None) -> dict:
        status, attempts = None, 5
        for attempt in range(attempts):
            wait = config.NVA_SLEEP - (time.monotonic() - self.last)
            if wait > 0:
                time.sleep(wait)
            self.last = time.monotonic()
            backoff = 10 * (attempt + 1)
            try:
                r = self.session.get(url, params=params, timeout=120)
                status = r.status_code
                if r.status_code == 200:
                    return r.json()
                if r.status_code == 400:
                    raise RuntimeError(f"NVA rejected the query: {r.text[:300]}")
                retry = (r.headers.get("Retry-After") or "").strip()
                if r.status_code == 429 and retry.isdigit():
                    backoff = min(int(retry), config.MAX_RETRY_AFTER)
            except requests.RequestException as exc:
                if attempt == attempts - 1:
                    raise
                status = type(exc).__name__
            if attempt < attempts - 1:   # no wait after the final attempt
                time.sleep(backoff)
        raise RuntimeError(f"Could not fetch {url} (last status: {status}); run again to resume")


def fetch_year(api: Api, year: int) -> tuple[list[dict], int]:
    """(records, totalHits) of one publication year."""
    params = {"unit": config.NVA_ORG, "publicationYear": year, "results": config.NVA_PAGE,
              "instanceTypeNot": ",".join(config.NVA_SKIPPED_TYPES), "aggregation": "none",
              "sort": "identifier"}  # searchAfter paging needs a fixed order
    page = api.get(config.NVA_SEARCH_URL, params)
    total, records = page.get("totalHits", 0), []
    while page.get("hits"):
        records.extend(trim(h) for h in page["hits"])
        print(f"  {year}: {len(records)}/{total}", end="\r", flush=True)
        nxt = page.get("nextSearchAfterResults")
        if not nxt or len(records) >= total:
            break
        page = api.get(nxt)
    print(f"  {year}: {len(records)} outputs" + " " * 20)
    return records, total


def incomplete(n_records: int, total: int, previous: int) -> str | None:
    """Why a fetched year must not replace the stored one (None: it may)."""
    if n_records < config.NVA_MIN_FETCHED_SHARE * total:
        return f"only {n_records} of {total} records fetched"
    if n_records == 0 and previous > 0:
        return f"no records returned (the stored file has {previous})"
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--full", action="store_true", help="fetch every year again")
    args = ap.parse_args()
    if not runlock.acquire():
        sys.exit("Another pipeline run is in progress (run_weekly.py or run_all.py): not started.")

    config.RAW_NVA.mkdir(parents=True, exist_ok=True)
    state = (json.loads(config.RAW_NVA_STATE.read_text(encoding="utf-8"))
             if config.RAW_NVA_STATE.exists() else {"years": {}})
    refresh_from = config.REFERENCE_YEAR - config.NVA_REFRESH_YEARS + 1
    years = [y for y in range(config.FIRST_YEAR, config.REFERENCE_YEAR + 2)
             if args.full or str(y) not in state["years"] or y >= refresh_from]
    print(f"NVA: fetching {len(years)} year(s): {', '.join(map(str, years)) or '-'}")
    api = Api()
    problems = []
    for year in years:
        records, total = fetch_year(api, year)
        previous = state["years"].get(str(year), {}).get("records", 0)
        why = incomplete(len(records), total, previous)
        if why:   # keep the stored file (if any); the year is fetched again next run
            problems.append(f"{year}: {why}")
            print(f"  {year}: {why} – previous data kept")
            continue
        fsutil.write_jsonl(config.RAW_NVA / f"{year}.jsonl", records)
        state["years"][str(year)] = {"fetched": datetime.now().isoformat(timespec="seconds"),
                                     "records": len(records)}
        fsutil.write_json(config.RAW_NVA_STATE, state, indent=1, ensure_ascii=True)
    print(f"Done. {sum(v['records'] for v in state['years'].values())} NVA outputs in {config.RAW_NVA}")
    if problems:
        print(f"Incomplete NVA years (previous data kept): {'; '.join(problems)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
