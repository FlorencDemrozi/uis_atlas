#!/usr/bin/env python3
"""
Stage 3 – Write a short overview and topic tags for each researcher (offline).

Input:  config.PROFILES, papers in config.RAW_ATLAS
Output: config.SUMMARIES  ({scopus_id: {summary, tags, source_hash, model}})

TODO (Claude Code) – implement:
- For each researcher, send up to config.SUMMARY_MAX_PAPERS papers (titles,
  keywords, abstracts; favour recent and well-cited) to the Claude API
  (model config.SUMMARY_MODEL, key from .env via config.ANTHROPIC_API_KEY).
- Ask for JSON only: {"summary": "...", "tags": ["...", ...]}
  * summary: 2–3 sentences, plain English understandable by industry partners,
    describing research areas and methods. Third person, no praise, no
    judgement of quality, no copied abstract sentences (DATA_POLICY §4).
  * tags: 3–6 short topic tags.
- Cache: store a hash of the input; skip researchers whose input is unchanged.
- Handle rate limits and retries; save progress after each researcher.
- Add a --sample N option that writes N summaries to a review file for the
  project owner to check before running on everyone.
"""


def main() -> None:
    raise NotImplementedError("Stage 3 not implemented yet – see docstring and docs/SPEC.md §3.1")


if __name__ == "__main__":
    main()
