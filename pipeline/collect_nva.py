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
import time
from datetime import datetime

import requests

import config
from nva import trim


class Api:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": config.USER_AGENT, "Accept": "application/json"})
        self.last = 0.0

    def get(self, url: str, params: dict | None = None) -> dict:
        status = None
        for attempt in range(5):
            wait = config.NVA_SLEEP - (time.monotonic() - self.last)
            if wait > 0:
                time.sleep(wait)
            self.last = time.monotonic()
            try:
                r = self.session.get(url, params=params, timeout=120)
                status = r.status_code
                if r.status_code == 200:
                    return r.json()
                if r.status_code == 400:
                    raise RuntimeError(f"NVA rejected the query: {r.text[:300]}")
            except requests.RequestException as exc:
                if attempt == 4:
                    raise
                status = type(exc).__name__
            time.sleep(10 * (attempt + 1))
        raise RuntimeError(f"Could not fetch {url} (last status: {status}); run again to resume")


def fetch_year(api: Api, year: int) -> list[dict]:
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
    return records


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--full", action="store_true", help="fetch every year again")
    args = ap.parse_args()

    config.RAW_NVA.mkdir(parents=True, exist_ok=True)
    state = (json.loads(config.RAW_NVA_STATE.read_text(encoding="utf-8"))
             if config.RAW_NVA_STATE.exists() else {"years": {}})
    refresh_from = config.REFERENCE_YEAR - config.NVA_REFRESH_YEARS + 1
    years = [y for y in range(config.FIRST_YEAR, config.REFERENCE_YEAR + 2)
             if args.full or str(y) not in state["years"] or y >= refresh_from]
    print(f"NVA: fetching {len(years)} year(s): {', '.join(map(str, years)) or '-'}")
    api = Api()
    for year in years:
        records = fetch_year(api, year)
        tmp = config.RAW_NVA / f"{year}.jsonl.tmp"
        with tmp.open("w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        tmp.replace(config.RAW_NVA / f"{year}.jsonl")
        state["years"][str(year)] = {"fetched": datetime.now().isoformat(timespec="seconds"),
                                     "records": len(records)}
        config.RAW_NVA_STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")
    print(f"Done. {sum(v['records'] for v in state['years'].values())} NVA outputs in {config.RAW_NVA}")


if __name__ == "__main__":
    main()
