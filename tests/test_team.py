"""Build a team: the method (pipeline/team.py), its browser mirror (web/src/team-core.ts)
and the licence rule for the published vectors (pipeline/team_vectors.py)."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import config  # noqa: E402
import team  # noqa: E402
import team_vectors  # noqa: E402

EXAMPLE = ("We could propose to develop and clinically validate multimodal digital biomarkers of disease "
           "progression in a chronic non-communicable disease, such as dementia or Parkinson’s disease. "
           "Established AI methods would combine existing clinical and biomarker data with continuous home "
           "data from wearables, environmental sensors, gamified tasks and automated daily-life questionnaires. "
           "This would predict functional decline and treatment response between clinic visits, giving "
           "clinicians earlier and more personalised decisions.")
TEXTS = [
    EXAMPLE,
    "Machine learning for predictive maintenance of offshore wind turbines",
    "We combine three areas: wearable sensors, machine learning, and nursing. The study runs in "
    "Stavanger, e.g. in home care; it involves patients, next of kin and nurses.",
    "Vi vil utvikle digitale verktøy for eldre, for eksempel sensorer, apper og spørreskjema. "
    "Prosjektet ser på helse, velferd, økonomi og etikk.",
    "  Spaces\tand\nnewlines , odd ,, commas, and \"quoted items\" (in brackets).  ",
]
S = config.TEAM_MATCH


def test_split_aspects_example():
    aspects = team.split_aspects(EXAMPLE, S["max_aspects"], S["max_item_words"])
    assert aspects[0] == EXAMPLE.rstrip(".")
    for item in ("dementia", "Parkinson’s disease", "wearables", "environmental sensors", "gamified tasks",
                 "automated daily-life questionnaires"):
        assert item in aspects
    assert len(aspects) == len({a.lower() for a in aspects}) <= S["max_aspects"]


def test_listed_items_get_their_sentence_as_context():
    pairs = team.split_aspects_with_context(EXAMPLE, S["max_aspects"], S["max_item_words"])
    ctx = dict(pairs)
    assert ctx["dementia"].startswith("We could propose") and ctx["wearables"].startswith("Established AI")
    assert ctx[pairs[0][0]] == "" and ctx[pairs[1][0]] == ""          # whole text and sentences: none
    items = team.list_items("We collect data on health, the taxonomy, and analyse consequences for equity", 6)
    assert items == ["health", "taxonomy", "equity"]


def test_context_lowers_people_outside_the_sentence():
    score = np.array([[0.0, 0.5], [1.0, 1.0]])   # aspect 0: the sentence, aspect 1: an item in it
    out = team.apply_context(score, ["s", "item"], ["", "s"], S)
    assert out[1, 0] == pytest.approx(S["context_floor"]) and out[1, 1] == 1.0
    assert np.array_equal(team.apply_context(score, ["s", "item"], ["", "removed"], S), score)


def test_split_aspects_short_query_is_one_aspect():
    assert team.split_aspects("wind energy", 12, 6) == ["wind energy"]


def test_scores_need_two_papers():
    rel = np.array([[1.0], [1.0], [0.9]])          # 3 papers, 1 aspect
    authors = [[0], [0], [1]]                        # person 0: two papers, person 1: one
    score, evidence = team.aspect_scores(rel, authors, 2, top=2, n_evidence=3)
    assert score[0, 0] == 1.0 and score[0, 1] == pytest.approx(0.45)
    assert [i for _, i in evidence[0][0]] == [0, 1]


def test_build_team_covers_aspects_and_prefers_coauthors():
    score = np.array([[1.0, 0.0, 0.0, 0.0],
                      [0.0, 0.8, 0.8, 0.0],
                      [0.0, 0.0, 0.0, 0.2]])
    co = [set(), set(), {0}, set()]                  # person 2 has papers with person 0
    cfg = dict(S, team_size=6, min_gain=0.3)
    members = team.build_team(score, [True] * 4, ["a", "b", "b", "c"], co, cfg)
    assert [m["person"] for m in members] == [0, 2]  # 2 beats 1 as co-author; 3 adds too little
    assert members[1]["adds"] == [(1, 0.8)]
    assert team.gaps(score, [True] * 4, 0.5) == [2]
    assert team.top_per_aspect(score, [True, False, True, True], 5) == [[0], [2], [3]]


def test_published_vectors_use_title_and_keywords_only():
    text = team_vectors.paper_text({"title": "A title", "keywords": ["k1", "k2"], "abstract": "SECRET ABSTRACT"})
    assert text == "A title. k1; k2" and "SECRET" not in text


def test_published_team_files():
    if not config.TEAM_VECTORS_META.exists():
        pytest.skip("team_vectors.py has not run")
    meta = json.loads(config.TEAM_VECTORS_META.read_text(encoding="utf-8"))
    assert meta["text"] == team_vectors.TEXT_RECIPE
    assert meta["model"] == config.EMBED_MODEL and meta["query_prefix"] == config.QUERY_PREFIX
    papers = json.loads((config.PUBLIC / "papers.json").read_text(encoding="utf-8"))
    assert set(meta["ids"]) <= set(papers), "team vectors for papers that are not public"
    # Settings are copied into team.json when it is written: a stale file breaks the website.
    assert meta["similarity"] == config.TEAM_MATCH["similarity"]["public"], "team.json is stale – run team_vectors.py"
    assert meta["settings"] == {k: config.TEAM_MATCH[k] for k in team_vectors.PUBLIC_SETTINGS}, \
        "team.json is stale – run team_vectors.py"
    _, ids, V = team.load_public()
    assert V.shape == (len(ids), meta["dim"])


# ---------------------------------------------------------------- parity with the browser
HARNESS = """
import { readFileSync } from "node:fs";
const core = await import(process.argv[2]);
const inp = JSON.parse(readFileSync(0, "utf8"));
const s = inp.settings;
const rel = inp.sims.map((col) => core.relevance(Float64Array.from(col), inp.similarity));
const raw = core.aspectScores(rel, inp.authors, inp.n_people, s.top_papers, s.evidence_papers);
const score = core.applyContext(raw.score, inp.names, inp.contexts, s);
const evidence = raw.evidence;
const co = core.coauthorSets(inp.all_authors, inp.n_people);
const out = {
  aspects: inp.texts.map((t) => core.splitAspectsWithContext(t, s.max_aspects, s.max_item_words)),
  floors: inp.sims.map((col) => core.floor(Float64Array.from(col), inp.similarity)),
  score: score.map((x) => [...x]),
  evidence: evidence.map((m) => Object.fromEntries([...m].map(([k, v]) => [k, v]))),
  team: core.buildTeam(score, inp.eligible, inp.dept, co, s),
  top: core.topPerAspect(score, inp.eligible, s.per_aspect),
  gaps: core.gaps(score, inp.eligible, s.covers),
};
process.stdout.write(JSON.stringify(out));
"""


def node_ok() -> bool:
    node = shutil.which("node")
    if not node:
        return False
    v = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip().lstrip("v")
    major, minor = (int(x) for x in v.split(".")[:2])
    return (major, minor) >= (22, 18)   # TypeScript files run without a flag


@pytest.mark.skipif(not node_ok(), reason="Node.js 22.18+ needed to run team-core.ts")
def test_browser_mirror_gives_the_same_answer(tmp_path):
    rng = np.random.default_rng(7)
    n_papers, n_people, m = 400, 60, 6
    sims = np.round(rng.normal(0.80, 0.03, size=(m, n_papers)), 6)   # aspects x papers
    authors = [sorted(set(rng.integers(0, n_people, size=rng.integers(1, 4)).tolist())) for _ in range(n_papers)]
    all_authors = authors + [sorted(set(rng.integers(0, n_people, size=3).tolist())) for _ in range(100)]
    eligible = [bool(x) for x in rng.random(n_people) > 0.15]
    dept = [f"d{x}" for x in rng.integers(0, 8, size=n_people)]
    settings = dict(S, team_size=6, min_gain=0.3)
    sim = {"min": 0.82, "percentile": 0.95, "width": 0.03}

    rel = np.stack([team.relevance(sims[j], sim) for j in range(m)], axis=1)
    raw, evidence = team.aspect_scores(rel, authors, n_people, settings["top_papers"], settings["evidence_papers"])
    names = [f"aspect {j}" for j in range(m)]
    contexts = ["", "", "aspect 0", "aspect 1", "", "not an aspect"]
    score = team.apply_context(raw, names, contexts, settings)
    assert not np.array_equal(score, raw), "fixture should exercise the context rule"
    co = team.coauthor_sets(all_authors, n_people)
    py = {
        "aspects": [[list(x) for x in team.split_aspects_with_context(t, settings["max_aspects"], settings["max_item_words"])]
                    for t in TEXTS],
        "floors": [team.floor(sims[j], sim) for j in range(m)],
        "team": team.build_team(score, eligible, dept, co, settings),
        "top": team.top_per_aspect(score, eligible, settings["per_aspect"]),
        "gaps": team.gaps(score, eligible, settings["covers"]),
    }
    script = tmp_path / "harness.mjs"
    script.write_text(HARNESS, encoding="utf-8")
    inp = {"texts": TEXTS, "sims": sims.tolist(), "similarity": sim, "settings": settings, "authors": authors,
           "all_authors": all_authors, "n_people": n_people, "eligible": eligible, "dept": dept,
           "names": names, "contexts": contexts}
    core = (ROOT / "web" / "src" / "team-core.ts").as_uri()
    res = subprocess.run(["node", str(script), core], input=json.dumps(inp), capture_output=True, text=True,
                         encoding="utf-8", timeout=60)
    assert res.returncode == 0, res.stderr
    js = json.loads(res.stdout)

    assert js["aspects"] == py["aspects"]
    assert js["floors"] == pytest.approx(py["floors"], abs=1e-12)
    assert np.allclose(np.array(js["score"]), score, atol=1e-9)
    for j in range(m):
        assert {int(k): [i for _, i in v] for k, v in js["evidence"][j].items()} == \
            {k: [i for _, i in v] for k, v in evidence[j].items()}
    assert [x["person"] for x in js["team"]] == [x["person"] for x in py["team"]]
    assert len(py["team"]) >= 2, "fixture should produce a real team"
    for a, b in zip(js["team"], py["team"]):
        assert a["gain"] == pytest.approx(b["gain"]) and [j for j, _ in a["adds"]] == [j for j, _ in b["adds"]]
    assert js["top"] == py["top"] and js["gaps"] == py["gaps"]


def test_typescript_mirror_has_the_same_rules():
    """The regular expressions and stop words are copied, not shared: catch a one-sided edit."""
    ts = (ROOT / "web" / "src" / "team-core.ts").read_text(encoding="utf-8")
    for name in ("CUE", "CONJ", "LEADING_CONJ", "ARTICLE", "LAST_PREP", "RELATIVE"):
        pattern = getattr(team, name).pattern
        assert re.search(rf"const {name} = /{re.escape(pattern)}/i;", ts), f"{name} differs between team.py and team-core.ts"
    assert all(w in ts for w in team.STOP)
