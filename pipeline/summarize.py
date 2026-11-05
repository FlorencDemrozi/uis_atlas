#!/usr/bin/env python3
"""
Stage 3 – Write a short overview and topic tags for each researcher (offline).

Input:  config.PROFILES, papers in config.PAPERS (build_profiles.py)
Output: config.SUMMARIES  ({scopus_id: {summary, tags, source_hash, paper_ids,
        prompt_version, name, model, generated}})

- Only papers from the last config.ACTIVE_YEARS years are used (project owner,
  2026-10-26); researchers without such papers get no summary (their cache entry
  is kept but not published). Entries of people who opted out are deleted.
- Up to config.SUMMARY_MAX_PAPERS papers per researcher (newest first, ties by
  paper id – never by citations): titles, keywords and abstracts go to the Claude
  API, which answers {"summary": "...", "tags": [...]} in a fixed JSON schema.
- Cached: a researcher is only sent again when a new paper enters their selection
  (papers that only age out keep the summary while at least half of the papers it
  was written from are still selected), or the model, prompt or name changes.
- Summaries that copy an abstract sentence are rejected (DATA_POLICY §4).
- Without ANTHROPIC_API_KEY no new summaries are written; it never fails the pipeline for that reason.

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
from fsutil import write_text

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


def select_ids(r: dict, papers: dict, by_citations: bool = False) -> list[str]:
    """Ids of the papers sent for a summary: publications first (lectures, artistic work
    and popular science fill the remaining slots), newest first, ties by paper id, so a
    weekly citation refresh never changes the selection. by_citations: the earlier rule
    (ties by citations), only to recognise cache entries written under it."""
    recent = [e for e in r["paper_ids"] if e in papers and config.is_active_paper(papers[e])]
    tie = (lambda e: (-(papers[e].get("citations") or 0), e)) if by_citations else (lambda e: (e,))
    recent.sort(key=lambda e: (not config.is_publication(papers[e]), -int(papers[e]["year"]), *tie(e)))
    return recent[:config.SUMMARY_MAX_PAPERS]


def select_papers(r: dict, papers: dict) -> list[dict]:
    return [papers[e] for e in select_ids(r, papers)]


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


def stable_hash(r: dict, selected: list[dict]) -> str:
    """Cache key that ignores the order of the selected papers (entries written when
    citations decided the order keep their key); only a change in which papers are
    selected, or in their text, changes it."""
    ordered = sorted(selected, key=lambda p: (not config.is_publication(p), -int(p["year"]), p["title"]))
    return source_hash(prompt_for(r, ordered))


def hashes(r: dict, selected: list[dict]) -> set[str]:
    """Every key an entry for exactly this selection may carry (the 2nd: entries from
    before stable_hash)."""
    return {stable_hash(r, selected), source_hash(prompt_for(r, selected))}


def still_fits(new_ids: list[str], basis: list[str]) -> bool:
    """A summary written from the papers in basis still describes the new selection
    when no paper entered it (papers only aged out or dropped) and at least half of
    basis is still selected. So 1 January does not redo every summary."""
    new, old = set(new_ids), set(basis)
    return new <= old and 2 * len(new & old) >= len(old)


def cached_basis(cached: dict, r: dict, papers: dict) -> list[str] | None:
    """The paper ids the cached summary was written from, if it can be kept, else None
    (a new summary is needed). A model, prompt or name change always needs one."""
    if not cached.get("summary"):
        return None
    ids = select_ids(r, papers)
    if "paper_ids" in cached:
        if (cached.get("model"), cached.get("prompt_version"), cached.get("name")) != (
                config.SUMMARY_MODEL, PROMPT_VERSION, r["name"]):
            return None
        return cached["paper_ids"] if still_fits(ids, cached["paper_ids"]) else None
    # Entries from before the paper ids were stored: the hash tells which papers they
    # were written from (the current rule, or the earlier citation tie-break).
    if cached.get("source_hash") in hashes(r, [papers[e] for e in ids]):
        return ids
    legacy = select_ids(r, papers, by_citations=True)
    if cached.get("source_hash") in hashes(r, [papers[e] for e in legacy]) and still_fits(ids, legacy):
        return legacy
    return None


def clean_tags(tags) -> list[str]:
    return [t.strip() for t in tags or [] if isinstance(t, str) and 0 < len(t.strip()) <= 50]


def valid(out: dict | None, abstracts: list[str]) -> str | None:
    """Reason the answer is unusable, or None if it is fine."""
    if not out or not out.get("summary", "").strip():
        return "empty answer"
    if len(out["summary"]) > 900:
        return "summary too long"
    tags = clean_tags(out.get("tags"))
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

    profiles = json.loads(config.PROFILES.read_text(encoding="utf-8"))["researchers"]
    papers = json.loads(config.PAPERS.read_text(encoding="utf-8"))
    cache = json.loads(config.SUMMARIES.read_text(encoding="utf-8")) if config.SUMMARIES.exists() else {}

    def save() -> None:   # temp file + rename: an interrupted run never leaves a broken cache
        write_text(config.SUMMARIES, json.dumps(cache, ensure_ascii=False, indent=1))

    # Summaries of people who opted out are deleted (also without a key). Entries of people
    # missing from this run's profiles, or without recent papers, are kept but never
    # published (export_public.py and embed.py use only current researchers with recent
    # papers): a collector that returned too little one week must not throw away
    # hundreds of paid summaries.
    excluded = set(json.loads(config.EXCLUSIONS.read_text(encoding="utf-8")).get("scopus_ids", [])) \
        if config.EXCLUSIONS.exists() else set()
    stale = [sid for sid in cache if sid in excluded]
    for sid in stale:
        del cache[sid]
    if stale:
        save()
        print(f"Removed {len(stale)} summaries of researchers who opted out.")

    cl = llm.client()
    if cl is None:
        print("No ANTHROPIC_API_KEY in .env – summaries skipped (the site works without them).")
        return

    todo = profiles
    if args.sample:
        todo = random.Random(42).sample(profiles, min(args.sample, len(profiles)))

    done, failed = [], []
    written = unchanged = no_recent = 0
    migrated = False

    try:
        for i, r in enumerate(todo, 1):
            ids = select_ids(r, papers)
            if not ids:
                no_recent += 1
                continue
            selected = [papers[e] for e in ids]
            text = prompt_for(r, selected)
            h = stable_hash(r, selected)
            cached = cache.get(r["scopus_id"], {})
            basis = cached_basis(cached, r, papers)
            if basis is not None:
                if "paper_ids" not in cached:   # older entry: store what it was written from
                    cached.update(paper_ids=basis, prompt_version=PROMPT_VERSION, name=r["name"])
                    if basis == ids:
                        cached["source_hash"] = h
                    migrated = True
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
                "tags": clean_tags(out["tags"])[:6],
                "source_hash": h,
                "paper_ids": ids,
                "prompt_version": PROMPT_VERSION,
                "name": r["name"],
                "model": config.SUMMARY_MODEL,
                "generated": datetime.now().isoformat(timespec="seconds"),
            }
            done.append(r)
            written += 1
            if written % 25 == 0:
                save()
            print(f"  [{i}/{len(todo)}] {r['name']}")

    finally:   # also on Ctrl+C or a fatal API error: keep what was written
        if written or migrated:
            save()

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
