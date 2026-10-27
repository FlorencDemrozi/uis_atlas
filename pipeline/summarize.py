#!/usr/bin/env python3
"""
Stage 3 – Write a short overview and topic tags for each researcher (offline).

Input:  config.PROFILES, papers in config.RAW_ATLAS
Output: config.SUMMARIES  ({scopus_id: {summary, tags, source_hash, model, generated}})

- Only papers from the last config.ACTIVE_YEARS years are used (project owner,
  2026-10-26); researchers without such papers get no summary.
- Up to config.SUMMARY_MAX_PAPERS papers per researcher (newest first, then most
  cited): titles, keywords and abstracts go to the Claude API, which answers
  {"summary": "...", "tags": [...]} in a fixed JSON schema.
- Cached: a researcher is only sent again when their input changes.
- Summaries that copy an abstract sentence are rejected (DATA_POLICY §4).
- Without ANTHROPIC_API_KEY the stage does nothing and the site shows no
  summaries; it never fails the pipeline for that reason.

Usage:
  python pipeline/summarize.py              # everyone whose input changed
  python pipeline/summarize.py --sample 20  # 20 random researchers + review CSV
"""
import argparse
import csv
import hashlib
import json
import random
from datetime import datetime

import config
import llm
from export_public import sentences

PROMPT_VERSION = 1

SYSTEM = """You write overviews of university researchers for a public research directory \
used by industry partners, public agencies and other researchers.

From the publications given, write:
- "summary": 2–3 sentences in plain English describing the person's research areas, \
methods and application domains. Third person, starting with the person's name. \
Describe only what the publications show. No praise, no judgement of quality or \
importance, no personal details. Use your own words: never copy a sentence or long \
phrase from the abstracts.
- "tags": 3–6 short topic tags (1–4 words each, lower case unless an acronym or \
proper name) that someone searching for this expertise would use."""

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "tags"],
    "additionalProperties": False,
}


def select_papers(r: dict, papers: dict) -> list[dict]:
    recent = [papers[e] for e in r["paper_ids"] if e in papers and config.is_active_paper(papers[e])]
    recent.sort(key=lambda p: (-int(p["year"]), -(p.get("citations") or 0)))
    return recent[:config.SUMMARY_MAX_PAPERS]


def prompt_for(r: dict, selected: list[dict]) -> str:
    blocks = []
    for p in selected:
        lines = [f"Title: {p['title']}", f"Year: {p['year']}"]
        if p.get("keywords"):
            lines.append("Keywords: " + "; ".join(p["keywords"]))
        if p.get("abstract"):
            lines.append("Abstract: " + p["abstract"])
        blocks.append("\n".join(lines))
    return f"Researcher: {r['name']}\n\n" + "\n\n---\n\n".join(blocks)


def source_hash(text: str) -> str:
    return hashlib.sha256(f"{config.SUMMARY_MODEL}|{PROMPT_VERSION}|{text}".encode()).hexdigest()


def valid(out: dict | None, abstracts: list[str]) -> str | None:
    """Reason the answer is unusable, or None if it is fine."""
    if not out or not out.get("summary", "").strip():
        return "empty answer"
    if len(out["summary"]) > 900:
        return "summary too long"
    tags = [t for t in out.get("tags", []) if isinstance(t, str) and 0 < len(t) <= 50]
    if not 3 <= len(tags) <= 6:
        return "wrong number of tags"
    corpus = " ".join(a.lower() for a in abstracts if a)
    if any(s in corpus for s in sentences(out["summary"])):
        return "copies an abstract sentence"
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--sample", type=int, help="summarise N random researchers and write a review CSV")
    args = ap.parse_args()

    cl = llm.client()
    if cl is None:
        print("No ANTHROPIC_API_KEY in .env – summaries skipped (the site works without them).")
        return

    profiles = json.loads(config.PROFILES.read_text(encoding="utf-8"))["researchers"]
    papers = json.loads(config.RAW_ATLAS.read_text(encoding="utf-8"))["papers"]
    cache = json.loads(config.SUMMARIES.read_text(encoding="utf-8")) if config.SUMMARIES.exists() else {}

    todo = profiles
    if args.sample:
        todo = random.Random(42).sample(profiles, min(args.sample, len(profiles)))

    done, failed = [], []
    written = unchanged = no_recent = 0
    for i, r in enumerate(todo, 1):
        selected = select_papers(r, papers)
        if not selected:
            no_recent += 1
            continue
        text = prompt_for(r, selected)
        h = source_hash(text)
        if cache.get(r["scopus_id"], {}).get("source_hash") == h:
            unchanged += 1
            done.append(r)
            continue
        out = None
        for _ in range(2):  # one retry if the answer fails the checks
            out = llm.ask_json(cl, SYSTEM, text, SCHEMA, effort="low")
            problem = valid(out, [p.get("abstract") for p in selected])
            if problem is None:
                break
        if problem:
            failed.append((r["name"], problem))
            print(f"  [{i}/{len(todo)}] {r['name']}: rejected ({problem})")
            continue
        cache[r["scopus_id"]] = {
            "summary": out["summary"].strip(),
            "tags": [t.strip() for t in out["tags"]][:6],
            "source_hash": h,
            "model": config.SUMMARY_MODEL,
            "generated": datetime.now().isoformat(timespec="seconds"),
        }
        config.SUMMARIES.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
        done.append(r)
        written += 1
        print(f"  [{i}/{len(todo)}] {r['name']}")

    if args.sample:
        config.REVIEW_DIR.mkdir(parents=True, exist_ok=True)
        out_csv = config.REVIEW_DIR / "summaries_sample.csv"
        with out_csv.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["scopus_id", "name", "department", "summary", "tags"])
            for r in done:
                s = cache.get(r["scopus_id"], {})
                w.writerow([r["scopus_id"], r["name"], r["department"], s.get("summary"), "; ".join(s.get("tags", []))])
        print(f"Review file: {out_csv}")
    print(f"Summaries: {written} written, {unchanged} unchanged, {no_recent} without recent papers, "
          f"{len(failed)} rejected.")


if __name__ == "__main__":
    main()
