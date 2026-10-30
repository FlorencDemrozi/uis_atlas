#!/usr/bin/env python3
"""
Stage 4d – Call vectors for the project idea search (offline).

Input:  config.CALLS, config.CALL_PROFILES (optional), config.FUNDING_MATCHES (aspects)
Output: config.CALL_VECTORS (float32 matrix), config.CALL_VECTORS_META

For every open or planned call that is matched on topic (not open to all fields, not
institution-level) three kinds of text are embedded with the atlas model:
  scope      the call as a whole (as in match_funding.call_aspects), "passage:" prefix
  aspect     the call's aspects (AI profile or official text), "passage:" prefix
  direction  example project directions from the AI profile, "query:" prefix – they
             are short ideas themselves, so idea and direction are compared like
             two queries
Vectors are cached by text, so a weekly run only embeds what changed. The scoring
(score_calls) is shared by idea_match.py and mirrored in web/src/ideas.ts.
"""
import hashlib
import json

import numpy as np

import config
import embed
import match_funding

CFG = config.IDEA_MATCH


def call_texts(call: dict, profile: dict | None) -> list[tuple[str, str, str]]:
    """[(kind, label, text)] for one call: scope first, then aspects and directions."""
    scope, aspects = match_funding.call_aspects(call, profile)
    title = match_funding.lang_text(call["fields"]["title"]["v"]) or call["id"]
    out = [("scope", title, scope)]
    out += [("aspect", a["label"], a["text"]) for a in aspects[:CFG["max_aspects"]]]
    interp = (profile or {}).get("profile", {}).get("interpretation", {})
    seen, dirs = set(), []
    for d in interp.get("explicit_directions", []) + interp.get("plausible_directions", []):
        if d and d.lower() not in seen:
            seen.add(d.lower())
            dirs.append(d)
    out += [("direction", d, d) for d in dirs[:CFG["max_directions"]]]
    return out


def searchable(call: dict) -> bool:
    f = call["fields"]
    return (f["status"]["v"] != "closed" and not f.get("open_field", {}).get("v")
            and not f.get("institution_level", {}).get("v"))


def key(kind: str, text: str) -> str:
    prefix = config.QUERY_PREFIX if kind == "direction" else config.PASSAGE_PREFIX
    return hashlib.sha1(f"{config.EMBED_MODEL}|{prefix}{text}".encode("utf-8")).hexdigest()


def load() -> tuple[dict, np.ndarray]:
    meta = json.loads(config.CALL_VECTORS_META.read_text(encoding="utf-8"))
    return meta, np.load(config.CALL_VECTORS)["v"]


def score_calls(q: np.ndarray, meta: dict, V: np.ndarray) -> list[tuple[float, str, int]]:
    """[(score, call id, index of the closest text)] best first, for a normalised idea vector q."""
    sims = V @ q
    out = []
    for c in meta["calls"]:
        kinds = [t[0] for t in c["texts"]]
        s = sims[c["start"]:c["start"] + len(kinds)]
        passage = [k for k, kind in enumerate(kinds) if kind != "direction"]
        directions = [k for k, kind in enumerate(kinds) if kind == "direction"]
        best_p = max(passage[1:], key=lambda k: s[k], default=0)
        score, best = 0.5 * s[0] + 0.5 * s[best_p], best_p
        if directions:
            d = max(directions, key=lambda k: s[k])
            if s[d] - CFG["direction_offset"] > score:
                score, best = float(s[d] - CFG["direction_offset"]), d
        out.append((float(score), c["id"], best))
    out.sort(key=lambda x: -x[0])
    return out


def main() -> None:
    calls = json.loads(config.CALLS.read_text(encoding="utf-8"))
    profiles = (json.loads(config.CALL_PROFILES.read_text(encoding="utf-8"))
                if config.CALL_PROFILES.exists() else {})
    cache: dict[str, np.ndarray] = {}
    if config.CALL_VECTORS.exists() and config.CALL_VECTORS_META.exists():
        meta, V = load()
        if meta.get("model") == config.EMBED_MODEL:
            cache = {k: V[i] for i, k in enumerate(meta["keys"])}
    entries, keys, todo = [], [], {}
    for call in calls["calls"]:
        if not searchable(call):
            continue
        texts = call_texts(call, profiles.get(call["id"]))
        entries.append({"id": call["id"], "start": len(keys), "texts": [[k, label] for k, label, _ in texts]})
        for kind, _, text in texts:
            h = key(kind, text)
            keys.append(h)
            if h not in cache:
                todo[h] = (kind, text)
    model = embed.load_model() if todo else None
    for kind in ("passage", "direction"):
        batch = [(h, t) for h, (k, t) in todo.items() if (k == "direction") == (kind == "direction")]
        if batch:
            prefix = config.QUERY_PREFIX if kind == "direction" else config.PASSAGE_PREFIX
            for h, v in zip([h for h, _ in batch], embed.encode(model, [t for _, t in batch], prefix)):
                cache[h] = v
    V = np.stack([cache[h] for h in keys]).astype(np.float32) if keys else np.zeros((0, 384), np.float32)
    np.savez_compressed(config.CALL_VECTORS, v=V)
    config.CALL_VECTORS_META.write_text(json.dumps({
        "model": config.EMBED_MODEL, "calls_from": calls.get("generated"), "settings": CFG,
        "keys": keys, "calls": entries}, ensure_ascii=False), encoding="utf-8")
    print(f"Call vectors: {len(entries)} calls, {len(keys)} texts ({len(todo)} newly embedded).")


if __name__ == "__main__":
    main()
