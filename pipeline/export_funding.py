#!/usr/bin/env python3
"""
Stage 5c – Export the Funding Intelligence data for the website, encrypted.

Input:  config.CALLS, config.CALLS_HISTORY, config.CALL_PROFILES (optional),
        config.FUNDING_MATCHES, config.PROFILES
Output: data/public/funding.enc.json

The funding pages are only for people who know the password (project owner,
2026-10-26). The site is static, so the data file itself is encrypted:
gzip -> AES-256-GCM with a key derived from the password (PBKDF2-SHA256,
600 000 iterations, random salt). The password is never in the site's code or
HTML; the browser derives the key only after it is typed in.

The password comes from ATLAS_FUNDING_PASSWORD in .env. Without it nothing is
written and the previous file stays as it is.

Contents: call records (fields with sources and evidence, change history,
review flags), AI call profiles when present, and matches with paper ids.
Only fields allowed below are exported; no abstracts or raw Scopus data
(DATA_POLICY §2) – papers are referenced by id and resolved against the public
papers.json.
"""
import base64
import gzip
import hashlib
import json
import os
import secrets
import sys
from datetime import datetime

import config

OUT = config.PUBLIC / "funding.enc.json"
ITERATIONS = 600_000
CALL_KEYS = ["id", "source", "family", "listing_group", "tags", "fetched", "fields", "review", "listed"]
SOURCES = {
    "rcn": {"name": "Research Council of Norway", "url": "https://www.forskningsradet.no/utlysninger/"},
    "eu": {"name": "EU Funding & Tenders Portal",
           "url": "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/calls-for-proposals"},
}


# Closed EU topics are kept for history only (about a thousand at any time): just
# what identifies them is exported, the portal link gives the rest. The website
# treats absent fields as "not specified".
CLOSED_EU_FIELDS = {"call_id", "title", "funder", "programme", "programme_part", "parent_call", "scheme",
                    "action_type", "status", "deadline", "preliminary_deadline", "full_proposal_deadline",
                    "opening_date", "total_budget", "min_amount", "max_amount", "expected_grants", "currency",
                    "url", "themes"}


def slim(call: dict) -> dict:
    """Keeps the file small: closed EU topics as above, and in every field the empty
    keys and a source URL equal to the call's own page are left out (web/src/funding.ts
    puts them back when the file is opened)."""
    if call["source"] == "eu" and call["fields"]["status"]["v"] == "closed":
        call["fields"] = {k: v for k, v in call["fields"].items() if k in CLOSED_EU_FIELDS}
    page = call["fields"].get("url", {}).get("v") or {}
    page = page.get("en") or page.get("nb") if isinstance(page, dict) else None
    call["fields"] = {k: {x: y for x, y in v.items() if y is not None and not (x == "url" and y == page)}
                      for k, v in call["fields"].items()}
    return call
HISTORY_PER_CALL = 15


def merge_ai(call: dict, profile: dict | None) -> None:
    """Add AI-read field values without overwriting what RCN states."""
    if not profile:
        return
    url = (call["fields"]["url"]["v"] or {}).get("en") or (call["fields"]["url"]["v"] or {}).get("nb")
    for key, fv in profile["profile"]["fields"].items():
        if fv["status"] == "not_specified":
            continue
        current = call["fields"].get(key)
        ai = {"v": fv["value"], "s": fv["status"], "ev": fv["evidence"] or None}
        if current is None or current["s"] == "not_specified":
            call["fields"][key] = {"v": {"en": fv["value"]}, "s": fv["status"], "src": "AI reading of the call text",
                                   "url": url, "ev": fv["evidence"] or None, "c": "medium", "m": "ai"}
        elif current.get("m") == "section":   # slim() drops empty keys
            current["ai"] = ai


def encrypt(plain: bytes, password: str) -> dict:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt, iv = secrets.token_bytes(16), secrets.token_bytes(12)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS, dklen=32)
    data = AESGCM(key).encrypt(iv, gzip.compress(plain), None)
    b64 = lambda b: base64.b64encode(b).decode("ascii")
    return {"format": "atlas-funding-1",
            "kdf": {"name": "PBKDF2", "hash": "SHA-256", "iterations": ITERATIONS, "salt": b64(salt)},
            "cipher": {"name": "AES-GCM", "iv": b64(iv)}, "compression": "gzip", "data": b64(data)}


def check_policy(text: str) -> None:
    for bad in ('"abstract"', '"affiliation_strings"', '"coauthor_ids"'):
        if bad in text:
            raise SystemExit(f"Licence check failed: funding export contains {bad}.")


def main() -> None:
    password = os.environ.get("ATLAS_FUNDING_PASSWORD")
    if not password:
        sys.exit("ATLAS_FUNDING_PASSWORD is not set in .env – funding data not exported "
                 "(the previous funding.enc.json, if any, is unchanged).")
    calls_doc = json.loads(config.CALLS.read_text(encoding="utf-8"))
    history = json.loads(config.CALLS_HISTORY.read_text(encoding="utf-8")) if config.CALLS_HISTORY.exists() else {}
    profiles = (json.loads(config.CALL_PROFILES.read_text(encoding="utf-8"))
                if config.CALL_PROFILES.exists() else {})
    matches_doc = json.loads(config.FUNDING_MATCHES.read_text(encoding="utf-8"))
    excluded = set(json.loads(config.EXCLUSIONS.read_text(encoding="utf-8")).get("scopus_ids", []))
    public_ids = {r["scopus_id"] for r in json.loads((config.PUBLIC / "researchers.json").read_text(encoding="utf-8"))}

    calls = []
    for c in calls_doc["calls"]:
        out = slim({k: c.get(k) for k in CALL_KEYS})
        prof = profiles.get(c["id"])
        merge_ai(out, prof)
        if prof:
            p = prof["profile"]
            out["profile"] = {k: p[k] for k in p if k != "fields"} | {"generated": prof["generated"],
                                                                        "model": prof["model"]}
        m = matches_doc["calls"].get(c["id"])
        if m:
            out["aspects"], out["aspect_basis"], out["title_terms"] = m["aspects"], m["aspect_basis"], m["title_terms"]
            if "open_eligibility" in m:  # open-field calls: offered to every researcher
                out["open_eligibility"] = {k: v for k, v in m["open_eligibility"].items()
                                           if k in public_ids and k not in excluded}
                out["eligibility_evidence"] = m["eligibility_evidence"]
        out["history"] = history.get(c["id"], [])[-HISTORY_PER_CALL:]
        calls.append(out)

    # Only researchers shown on the public site (respects exclusions/opt-outs).
    matches = {}
    for cid, m in matches_doc["calls"].items():
        keep = []
        for x in m["matches"]:
            if x["id"] not in public_ids or x["id"] in excluded:
                continue
            x = dict(x, collaborators=[k for k in x["collaborators"] if k["id"] in public_ids])
            keep.append(x)
        matches[cid] = keep

    profiles_meta = [p["generated"] for p in profiles.values()]
    data = {
        "meta": {
            "generated": datetime.now().isoformat(timespec="seconds"),
            "sources": [dict(SOURCES[src], id=src, **(st or {})) for src, st in (calls_doc.get("sync") or {}).items()
                        if src in SOURCES],
            "calls_extracted": calls_doc["generated"],
            "profiles_generated": max(profiles_meta) if profiles_meta else None,
            "matches_generated": matches_doc["generated"],
            "researchers_updated": matches_doc.get("researchers_from"),
            "papers_from_year": matches_doc.get("papers_from_year"),
            "algorithm": matches_doc["algorithm"],
            "weights": matches_doc["settings"]["weights"],
            "categories": matches_doc["settings"]["categories"],
            "has_ai_profiles": bool(profiles),
        },
        "calls": calls,
        "matches": matches,
    }
    plain = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    check_policy(plain)
    OUT.write_text(json.dumps(encrypt(plain.encode("utf-8"), password)), encoding="utf-8")
    print(f"Funding data: {len(calls)} calls, {sum(len(v) for v in matches.values())} matches -> {OUT.name} "
          f"({OUT.stat().st_size / 1e6:.2f} MB encrypted, {len(plain) / 1e6:.2f} MB plain).")


if __name__ == "__main__":
    main()
