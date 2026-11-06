"""
Build a team: the matching method shared by the website and team_match.py.

A project description is split into aspects (split_aspects); each aspect is compared
with every recent paper; a researcher's score for an aspect is the mean relevance of
their config.TEAM_MATCH["top_papers"] best papers, so one lucky paper is not enough;
a team is then picked one person at a time, each time the person who adds the most
coverage of aspects not yet covered (build_team).

Mirrored line by line in web/src/team-core.ts; tests/test_team.py runs both on the
same inputs and checks that they agree. Change both together.

The regular expressions use re.ASCII, so \\b and case folding behave as in
JavaScript.
"""
import re

import numpy as np

A = re.ASCII | re.IGNORECASE
# Sentence ends: . ! ? before a capital, digit or quote ("e.g. dementia" stays whole); ; and : always.
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(ÆØÅ])|(?<=[;:])\s+", A & ~re.IGNORECASE)
# Words that introduce examples: what follows is a list of aspects.
CUE = re.compile(r"\b(?:such as|for example|for instance|e\.g\.|including|for eksempel|slik som|f\.eks\.|blant annet|bl\.a\.|inkludert)\s+", A)
CONJ = re.compile(r"\s+(?:and|or|as well as|og|eller|samt)\s+", A)
LEADING_CONJ = re.compile(r"^(?:and|or|og|eller|samt)\s+", A)
ARTICLE = re.compile(r"^(?:the|a|an)\s+", A)
# The words after the last preposition of a clause: "... home data from wearables" -> "wearables".
LAST_PREP = re.compile(r"^.*\b(?:from|with|of|on|in|using|via|by|for|to|fra|med|av|på|ved|gjennom|om)\s+", A)
RELATIVE = re.compile(r"^(?:which|that|who|where|som|der|hvor)\b", A)
TRIM = re.compile(r"^[\s\"'(\[]+|[\s\"')\].,;:!?]+$")
STOP = set(("a an and are as at be by for from in into is of on or the to with without using via based this that "
            "these those we our its it would could will can may og i på av for med til en et den det som om fra ved "
            "under mellom vi vår").split())


def words(s: str) -> list[str]:
    return [w for w in s.split(" ") if w]


def clean(s: str) -> str:
    return TRIM.sub("", " ".join(words(s)))


def usable(item: str, max_words: int) -> bool:
    w = words(item)
    return (0 < len(w) <= max_words and len(item) >= 3 and not RELATIVE.search(item)
            and any(x.lower() not in STOP for x in w))


def item(part: str) -> str:
    """One listed thing: without a leading "and"/"the"; a longer phrase is cut to the
    words after its last preposition ("analyse consequences for equity" -> "equity")."""
    p = clean(ARTICLE.sub("", LEADING_CONJ.sub("", clean(part))))
    return clean(LAST_PREP.sub("", p)) if len(words(p)) > 3 else p


def list_items(sentence: str, max_words: int) -> list[str]:
    """The listed things in one sentence: after "such as" and the like, or in a list
    of three or more comma-separated parts."""
    cue = CUE.search(sentence)
    if cue:
        parts = []
        for p in sentence[cue.end():].split(","):
            parts += CONJ.split(LEADING_CONJ.sub("", clean(p)))
        items = [item(p) for p in parts]
        return [p for p in items if usable(p, max_words)]
    parts = [clean(p) for p in sentence.split(",")]
    if len(parts) < 3:
        return []
    first = LAST_PREP.sub("", parts[0])
    last = CONJ.split(LEADING_CONJ.sub("", parts[-1]), maxsplit=1)
    items = [item(p) for p in [first] + parts[1:-1] + last]
    return [p for p in items if usable(p, max_words)]


def split_aspects_with_context(text: str, max_aspects: int, max_words: int) -> list[tuple[str, str]]:
    """[(aspect, context)]: the whole description first, then each sentence (three words
    or more) followed by the things it lists. The context of a listed thing is the
    sentence it comes from (or the whole description when that is the same sentence);
    "" for the rest. Duplicates are dropped."""
    whole = clean(re.sub(r"\s+", " ", text))
    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(s: str, ctx: str) -> None:
        key = s.lower()
        if s and key not in seen and len(out) < max_aspects:
            seen.add(key)
            out.append((s, ctx))

    add(whole, "")
    for s in SENTENCE_END.split(whole):
        s = clean(s)
        if len(words(s)) >= 3:
            add(s, "")
        ctx = s if s.lower() in seen else ""
        for x in list_items(s, max_words):
            add(x, next(a for a, _ in out if a.lower() == s.lower()) if ctx else "")
    return out


def split_aspects(text: str, max_aspects: int, max_words: int) -> list[str]:
    return [a for a, _ in split_aspects_with_context(text, max_aspects, max_words)]


def apply_context(score: np.ndarray, aspects: list[str], contexts: list[str], cfg: dict) -> np.ndarray:
    """A listed thing counts in the context of its sentence: a person's score for it is
    multiplied by context_floor + (1 - context_floor) x min(1, their score for that
    sentence / context_full). "agitation" from a sentence on dementia care then
    favours dementia researchers over chemists. Aspects whose context is not among
    the aspects (removed, or added by hand) are left as they are."""
    out = score.copy()
    index = {a: k for k, a in enumerate(aspects)}
    for j, ctx in enumerate(contexts):
        k = index.get(ctx) if ctx else None
        if k is None or k == j:
            continue
        factor = cfg["context_floor"] + (1 - cfg["context_floor"]) * np.minimum(1.0, score[k] / cfg["context_full"])
        out[j] = score[j] * factor
    return out


def floor(sims: list[float] | np.ndarray, sim: dict) -> float:
    """The similarity at which a paper starts to count for one aspect: the value at
    rank floor(percentile x (n - 1)) of the sorted similarities, at least sim["min"]."""
    s = sorted(float(x) for x in sims)
    return max(sim["min"], s[int(sim["percentile"] * (len(s) - 1))]) if s else sim["min"]


def relevance(sims: np.ndarray, sim: dict) -> np.ndarray:
    """Relevance of every paper for one aspect, 0 at the floor, 1 at floor + width."""
    lo = floor(sims, sim)
    return np.clip((np.asarray(sims, dtype=np.float64) - lo) / sim["width"], 0.0, 1.0)


def aspect_scores(rel: np.ndarray, authors: list[list[int]], n_people: int, top: int, n_evidence: int):
    """rel: papers x aspects relevance. Returns (score, evidence): score[j][r] is the mean
    relevance of person r's `top` best papers for aspect j; evidence[j][r] their best
    papers [(relevance, paper row)], at most n_evidence."""
    m = rel.shape[1]
    score = np.zeros((m, n_people))
    evidence: list[dict[int, list[tuple[float, int]]]] = []
    for j in range(m):
        per: dict[int, list[tuple[float, int]]] = {}
        col = rel[:, j]
        for i in np.nonzero(col > 0)[0].tolist():
            for a in authors[i]:
                per.setdefault(a, []).append((float(col[i]), i))
        ev = {}
        for a, lst in per.items():
            lst.sort(key=lambda x: (-x[0], x[1]))
            score[j, a] = sum(x[0] for x in lst[:top]) / top
            ev[a] = lst[:max(top, n_evidence)]
        evidence.append(ev)
    return score, evidence


def build_team(score: np.ndarray, eligible: list[bool], dept: list[str], coauthors: list[set[int]], cfg: dict) -> list[dict]:
    """Greedy coverage: each round adds the eligible person whose scores add most above
    what the team already covers (at least cfg["min_gain"]); someone who has papers
    with a team member, or comes from a department not yet in the team, is preferred
    when the gains are close. [{"person", "gain", "adds": [(aspect, added)] largest first}]."""
    m, n = score.shape
    covered = [0.0] * m
    team: list[dict] = []
    chosen: set[int] = set()
    depts: set[str] = set()
    while len(team) < cfg["team_size"]:
        best, best_val, best_gain = -1, 0.0, 0.0
        for r in range(n):
            if not eligible[r] or r in chosen:
                continue
            gain = 0.0
            for j in range(m):
                d = score[j, r] - covered[j]
                if d > 0:
                    gain += d
            if gain < cfg["min_gain"]:
                continue
            val = gain
            if any(t in coauthors[r] for t in chosen):
                val *= 1 + cfg["coauthor_bonus"]
            if team and dept[r] not in depts:
                val *= 1 + cfg["new_department_bonus"]
            if val > best_val:
                best, best_val, best_gain = r, val, gain
        if best < 0:
            break
        adds = [(j, float(score[j, best] - covered[j])) for j in range(m) if score[j, best] > covered[j]]
        adds.sort(key=lambda x: (-x[1], x[0]))
        for j in range(m):
            covered[j] = max(covered[j], float(score[j, best]))
        team.append({"person": best, "gain": best_gain, "adds": adds})
        chosen.add(best)
        depts.add(dept[best])
    return team


def top_per_aspect(score: np.ndarray, eligible: list[bool], k: int) -> list[list[int]]:
    """Per aspect the k eligible people with the highest score (above 0), ties by order."""
    out = []
    for j in range(score.shape[0]):
        people = [r for r in range(score.shape[1]) if eligible[r] and score[j, r] > 0]
        people.sort(key=lambda r: (-score[j, r], r))
        out.append(people[:k])
    return out


def gaps(score: np.ndarray, eligible: list[bool], covers: float) -> list[int]:
    """Aspects nobody eligible covers (best score below `covers`)."""
    return [j for j in range(score.shape[0])
            if max((score[j, r] for r in range(score.shape[1]) if eligible[r]), default=0.0) < covers]


def coauthor_sets(paper_authors: list[list[int]], n_people: int) -> list[set[int]]:
    """For each person, everyone who shares at least one paper with them."""
    out: list[set[int]] = [set() for _ in range(n_people)]
    for authors in paper_authors:
        for a in authors:
            out[a].update(authors)
    for a in range(n_people):
        out[a].discard(a)
    return out


def load_public() -> tuple[dict, list[str], np.ndarray]:
    """(metadata, paper ids, vectors as float64) from the published team files, exactly
    as the website reads them (int8 x scale). ValueError if the files do not match."""
    import base64
    import hashlib
    import json

    import config
    meta = json.loads(config.TEAM_VECTORS_META.read_text(encoding="utf-8"))
    data = config.TEAM_VECTORS.read_bytes()
    if hashlib.sha1(data).hexdigest() != meta["sha1"] or len(data) != len(meta["ids"]) * meta["dim"]:
        raise ValueError("team.vectors.bin and team.json do not match – run: python pipeline/team_vectors.py")
    values = np.frombuffer(data, dtype=np.int8).reshape(len(meta["ids"]), meta["dim"]).astype(np.float64)
    scales = np.frombuffer(base64.b64decode(meta["scales"]), dtype="<f4").astype(np.float64)
    return meta, meta["ids"], values * scales[:, None]
