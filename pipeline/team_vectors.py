#!/usr/bin/env python3
"""
Stage 5b – Paper vectors for "Build a team" on the website (published).

Input:  data/public/papers.json and researchers.json (written by export_public.py)
Output: config.TEAM_VECTORS       int8, one row per recent paper, row-major
        config.TEAM_VECTORS_META  {"model", "passage_prefix", "query_prefix", "text",
                                   "settings", "dim", "ids", "scales", "sha1"}
        config.TEAM_CACHE_DIR/team_papers.npy/.json   float32 cache (local)

Licence: the vectors are made only from what data/public/papers.json already
publishes – the title and keywords – never from abstracts (project owner,
2026-11-06; DATA_POLICY §2). Reading the public file, not data/interim/, makes
that hold by construction; tests/test_team.py checks the recorded text recipe.

Papers: the last config.ACTIVE_YEARS years, topical categories (config.is_active_paper),
with at least one researcher on the site. Same model and "passage:" prefix as
embed.py; vectors are cached by text, so a weekly run only embeds new or changed
titles. Each vector is stored as int8 with one float32 scale (error < 0.5 % of a
component; rankings do not change). The .json records a checksum of the .bin, so
the website can tell when the two come from different runs.
"""
import base64
import hashlib
import json

import numpy as np

import config
import embed
from fsutil import write_bytes, write_text

CACHE_NPY = config.TEAM_CACHE_DIR / "team_papers.npy"
CACHE_META = config.TEAM_CACHE_DIR / "team_papers.json"
TEXT_RECIPE = "title + keywords from data/public/papers.json"
PUBLIC_SETTINGS = ["algorithm", "top_papers", "covers", "per_aspect", "evidence_papers", "team_size",
                   "min_gain", "coauthor_bonus", "new_department_bonus", "context_floor", "context_full",
                   "max_aspects", "max_item_words"]


def category(p: dict) -> str:
    """As export_public.default_category: papers.json leaves out the default category."""
    if p.get("category"):
        return p["category"]
    return config.category_of(p["type"]) if p.get("type") else "article"


def paper_text(p: dict) -> str:
    """Title and keywords only: the published fields (never an abstract)."""
    parts = [p.get("title") or "", "; ".join(p.get("keywords") or [])]
    return ". ".join(x.strip() for x in parts if x and x.strip())


def recent_papers(papers: dict, people: set[str]) -> dict[str, str]:
    """{paper id: text} for recent topical papers with an author on the site."""
    out = {}
    for eid, p in papers.items():
        if set(p.get("uis_author_ids") or []) & people and \
                config.is_active_paper({"year": p.get("year"), "category": category(p)}):
            text = paper_text(p)
            if text:
                out[eid] = text
    return out


def quantise(V: np.ndarray) -> tuple[bytes, np.ndarray]:
    """Unit vectors -> (int8 bytes, float32 scale per row)."""
    scale = (np.maximum(np.abs(V).max(axis=1), 1e-9) / 127).astype(np.float32) if len(V) else np.zeros(0, np.float32)
    q = np.round(V / scale[:, None]).astype(np.int8) if len(V) else np.zeros((0, V.shape[1]), np.int8)
    return q.tobytes(), scale


def embed_texts(texts: dict[str, str]) -> tuple[list[str], np.ndarray]:
    """Vectors for {id: text}, reusing cached rows whose text is unchanged."""
    cached = {}
    loaded = embed.load_matrix(CACHE_NPY, CACHE_META)
    if loaded and loaded[0].get("model") == config.EMBED_MODEL:
        meta, old = loaded
        cached = {(i, h): old[k] for k, (i, h) in enumerate(zip(meta["ids"], meta["hashes"]))}
    ids = sorted(texts)
    hashes = [embed.text_hash(texts[i]) for i in ids]
    missing = [k for k, key in enumerate(zip(ids, hashes)) if key not in cached]
    print(f"Team vectors: {len(ids)} recent papers, {len(ids) - len(missing)} cached, {len(missing)} to embed")
    model = embed.load_model() if missing or not cached else None
    if missing:
        new = embed.encode(model, [texts[ids[k]] for k in missing], config.PASSAGE_PREFIX)
        dim = new.shape[1]
    else:
        dim = next(iter(cached.values())).shape[0] if cached else embed.encode(model, [], config.PASSAGE_PREFIX).shape[1]
        new = np.zeros((0, dim), np.float32)
    fresh = dict(zip(missing, new))
    matrix = np.zeros((len(ids), dim), dtype=np.float32)
    for k, key in enumerate(zip(ids, hashes)):
        matrix[k] = fresh[k] if k in fresh else cached[key]
    embed.save_matrix(CACHE_NPY, CACHE_META, matrix, {"model": config.EMBED_MODEL, "ids": ids, "hashes": hashes})
    return ids, matrix


def main() -> None:
    papers = json.loads((config.PUBLIC / "papers.json").read_text(encoding="utf-8"))
    researchers = json.loads((config.PUBLIC / "researchers.json").read_text(encoding="utf-8"))
    ids, matrix = embed_texts(recent_papers(papers, {r["scopus_id"] for r in researchers}))
    data, scales = quantise(matrix)
    write_bytes(config.TEAM_VECTORS, data)
    write_text(config.TEAM_VECTORS_META, json.dumps({
        "model": config.EMBED_MODEL, "passage_prefix": config.PASSAGE_PREFIX, "query_prefix": config.QUERY_PREFIX,
        "text": TEXT_RECIPE, "from_year": config.ACTIVE_FROM,
        "similarity": config.TEAM_MATCH["similarity"]["public"],
        "settings": {k: config.TEAM_MATCH[k] for k in PUBLIC_SETTINGS},
        "dim": int(matrix.shape[1]), "ids": ids,
        "scales": base64.b64encode(scales.astype("<f4").tobytes()).decode("ascii"),
        "sha1": hashlib.sha1(data).hexdigest(),
    }, separators=(",", ":")))
    print(f"Wrote {config.TEAM_VECTORS.name} ({len(data) / 1e6:.1f} MB) and {config.TEAM_VECTORS_META.name}.")


if __name__ == "__main__":
    main()
