#!/usr/bin/env python3
"""
Stage 4 – Compute semantic embeddings for papers and researchers.

Input:  config.PROFILES, config.SUMMARIES, papers in config.RAW_ATLAS
Output: config.EMBEDDINGS_DIR/ (paper vectors, researcher vectors, id index)

TODO (Claude Code) – implement (docs/SPEC.md §4):
- Model: config.EMBED_MODEL via sentence-transformers, normalised vectors.
- Papers: config.PASSAGE_PREFIX + title + keywords + abstract.
- Researchers: config.PASSAGE_PREFIX + summary + tags.
- Store as float32; also produce a compact version for the web (float16 or
  int8-quantised) and report its size in MB.
- Embedding vectors are derived data; they may be published only after the
  UiS Library confirms (DATA_POLICY §2).
"""


def main() -> None:
    raise NotImplementedError("Stage 4 not implemented yet – see docstring and docs/SPEC.md §4")


if __name__ == "__main__":
    main()
