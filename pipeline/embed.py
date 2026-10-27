#!/usr/bin/env python3
"""
Stage 4 – Compute semantic embeddings for papers and researchers.

Input:  config.PROFILES, config.SUMMARIES (optional), papers in config.RAW_ATLAS
Output: config.EMBEDDINGS_DIR/
          papers.npy       float32, one normalised row per paper
          papers.json      {"model", "ids", "hashes"}
          researchers.npy  float32, one normalised row per researcher
          researchers.json {"model", "ids", "n_papers", "has_summary"}

- Model: config.EMBED_MODEL (sentence-transformers), the same model and prefixes
  the browser uses (SPEC §4.1).
- Only papers from the last config.ACTIVE_YEARS years (project owner, 2026-10-26).
- Papers: config.PASSAGE_PREFIX + title + keywords + abstract. Cached by text
  hash, so a weekly run only embeds new or changed papers.
- Researcher vector: mean of their recent paper vectors, averaged with the
  vector of their summary and tags when a summary exists.
- Vectors are derived from licensed abstracts and stay local (data/interim/)
  until the UiS Library confirms they may be published (DATA_POLICY §2). The
  funding matcher (match_funding.py) uses them offline.
"""
import hashlib
import json

import numpy as np

import config

PAPERS_NPY = config.EMBEDDINGS_DIR / "papers.npy"
PAPERS_META = config.EMBEDDINGS_DIR / "papers.json"
RESEARCHERS_NPY = config.EMBEDDINGS_DIR / "researchers.npy"
RESEARCHERS_META = config.EMBEDDINGS_DIR / "researchers.json"


def load_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(config.EMBED_MODEL)


def encode(model, texts: list[str], prefix: str) -> np.ndarray:
    if not texts:
        dim = getattr(model, "get_embedding_dimension", None) or model.get_sentence_embedding_dimension
        return np.zeros((0, dim()), dtype=np.float32)
    vecs = model.encode([prefix + t for t in texts], batch_size=32, normalize_embeddings=True,
                        show_progress_bar=len(texts) > 200, convert_to_numpy=True)
    return vecs.astype(np.float32)


def normalise(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.where(n == 0, 1, n)


def paper_text(p: dict) -> str:
    parts = [p.get("title") or "", "; ".join(p.get("keywords") or []), p.get("abstract") or ""]
    return ". ".join(x.strip() for x in parts if x and x.strip())


def text_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def load_papers() -> tuple[list[str], np.ndarray]:
    """Paper ids and their vectors (for later stages)."""
    meta = json.loads(PAPERS_META.read_text(encoding="utf-8"))
    return meta["ids"], np.load(PAPERS_NPY)


def embed_papers(model, texts: dict[str, str]) -> tuple[list[str], np.ndarray]:
    """Embed {id: text}, reusing cached rows whose text is unchanged."""
    cached = {}
    if PAPERS_META.exists() and PAPERS_NPY.exists():
        meta = json.loads(PAPERS_META.read_text(encoding="utf-8"))
        if meta.get("model") == config.EMBED_MODEL:
            old = np.load(PAPERS_NPY)
            cached = {(i, h): old[k] for k, (i, h) in enumerate(zip(meta["ids"], meta["hashes"]))}
    ids = sorted(texts)
    hashes = [text_hash(texts[i]) for i in ids]
    missing = [k for k, key in enumerate(zip(ids, hashes)) if key not in cached]
    print(f"Papers: {len(ids)} recent, {len(ids) - len(missing)} cached, {len(missing)} to embed")
    new = encode(model, [texts[ids[k]] for k in missing], config.PASSAGE_PREFIX)
    dim = new.shape[1] if len(missing) else next(iter(cached.values())).shape[0]
    matrix = np.zeros((len(ids), dim), dtype=np.float32)
    fresh = dict(zip(missing, new))
    for k, key in enumerate(zip(ids, hashes)):
        matrix[k] = fresh[k] if k in fresh else cached[key]
    config.EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)
    np.save(PAPERS_NPY, matrix)
    PAPERS_META.write_text(json.dumps({"model": config.EMBED_MODEL, "ids": ids, "hashes": hashes}),
                           encoding="utf-8")
    return ids, matrix


def main() -> None:
    profiles = json.loads(config.PROFILES.read_text(encoding="utf-8"))["researchers"]
    papers = json.loads(config.RAW_ATLAS.read_text(encoding="utf-8"))["papers"]
    summaries = (json.loads(config.SUMMARIES.read_text(encoding="utf-8"))
                 if config.SUMMARIES.exists() else {})

    recent = {e: paper_text(papers[e]) for r in profiles for e in r["paper_ids"]
              if e in papers and config.is_active_paper(papers[e])}
    model = load_model()
    ids, matrix = embed_papers(model, recent)
    row = {e: k for k, e in enumerate(ids)}

    people = [r for r in profiles if any(e in row for e in r["paper_ids"])]
    with_summary = [r for r in people if summaries.get(r["scopus_id"], {}).get("summary")]
    summary_vecs = dict(zip(
        [r["scopus_id"] for r in with_summary],
        encode(model, [summaries[r["scopus_id"]]["summary"] + " " + "; ".join(summaries[r["scopus_id"]]["tags"])
                       for r in with_summary], config.PASSAGE_PREFIX)))
    vecs, n_papers = [], []
    for r in people:
        rows = [row[e] for e in r["paper_ids"] if e in row]
        v = normalise(matrix[rows].mean(axis=0))
        if r["scopus_id"] in summary_vecs:
            v = normalise(v + summary_vecs[r["scopus_id"]])
        vecs.append(v)
        n_papers.append(len(rows))
    np.save(RESEARCHERS_NPY, np.array(vecs, dtype=np.float32))
    RESEARCHERS_META.write_text(json.dumps({
        "model": config.EMBED_MODEL, "ids": [r["scopus_id"] for r in people], "n_papers": n_papers,
        "has_summary": [r["scopus_id"] in summary_vecs for r in people]}), encoding="utf-8")
    print(f"Researchers: {len(people)} with papers since {config.ACTIVE_FROM} "
          f"({len(summary_vecs)} with summary); {len(profiles) - len(people)} without.")
    print(f"Vectors in {config.EMBEDDINGS_DIR} ({matrix.nbytes / 1e6:.1f} MB float32; local only).")


if __name__ == "__main__":
    main()
