"""Project builder, "Prepare AI prompt": web/src/prompt-core.ts, run with Node."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from test_team import node_ok

ROOT = Path(__file__).resolve().parent.parent
CORE = (ROOT / "web" / "src" / "prompt-core.ts").as_uri()
HARNESS = """
import { readFileSync } from "node:fs";
const p = await import(process.argv[2]);
const inp = JSON.parse(readFileSync(0, "utf8"));
const pkg = p.buildPrompt(inp);
process.stdout.write(JSON.stringify({ ...pkg, plain: p.toPlainText(pkg.prompt).slice(0, 200) }));
"""


def build(tmp_path, inp: dict) -> dict:
    script = tmp_path / "harness.mjs"
    script.write_text(HARNESS, encoding="utf-8")
    res = subprocess.run([shutil.which("node"), str(script), CORE], input=json.dumps(inp), capture_output=True,
                         text=True, encoding="utf-8", timeout=60)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def call(k: int, scope: str = "Digital biomarkers for neurodegenerative disease.") -> dict:
    return {"id": f"call-{k}", "title": f"Call title {k}", "url": f"https://funder.example/call-{k}", "funder": "Funder",
            "collected": "2026-11-01",
            "sections": [{"title": "Scope and objectives", "fields": [
                {"label": "Scope", "value": scope, "evidence": "explicit"},
                {"label": "Priorities", "value": "", "evidence": "missing"}]},
                {"title": "AI reading of the call (generated; not official text)", "fields": [
                    {"label": "Objectives", "value": "Earlier diagnosis", "evidence": "ai"}]}],
            "missing": ["Evaluation criteria", "Budget or grant size"]}


def person(k: int, n_papers: int = 3) -> dict:
    return {"id": f"r{k}", "name": f"Researcher {k}", "position": "Professor", "unit": "Dept, Faculty",
            "profile": f"https://atlas.example/#/r/r{k}", "links": [], "summary": "Works on wearables.",
            "topics": ["wearables"], "matches": [{"call": 0, "category": "high"}],
            "papers": [{"title": f"Paper {i}", "year": "2025", "venue": "J", "link": "", "forCalls": [0] if i == 0 else []}
                       for i in range(n_papers)]}


def base(**kw) -> dict:
    inp = {"calls": [call(1)], "researchers": [person(1)],
           "prefs": {"direction": "early detection", "area": "", "constraints": ""},
           "answerLanguage": "Norwegian (bokmål)", "dates": {"today": "2026-11-06", "atlas": "2026-11-02", "funding": "2026-11-03"},
           "inlineLimit": 60000, "fieldLimit": 6000}
    inp.update(kw)
    return inp


@pytest.mark.skipif(not node_ok(), reason="Node.js 22.18+ needed to run prompt-core.ts")
def test_prompt_holds_exactly_the_selection_and_the_rules(tmp_path):
    out = build(tmp_path, base(calls=[call(1), call(2)], researchers=[person(1), person(2)]))
    p = out["prompt"]
    assert out["support"] is None and out["omitted"] == []
    for x in ("Call 1: Call title 1", "Call 2: Call title 2", "R1: Researcher 1", "R2: Researcher 2"):
        assert x in p
    assert "Call title 3" not in p
    # Required behaviour of the external model.
    for rule in ("do not force a", "Never invent", "[Assumption]", "**unverified**", "Write the answer in Norwegian (bokmål)",
                 "Project title and acronym", "Missing expertise or partners", "Sources and assumptions"):
        assert rule in p, rule
    # Missing requirements are named; empty fields are left out; AI text is labelled.
    assert "### Not found in the collected call text\n- Evaluation criteria\n- Budget or grant size" in p
    assert "Priorities" not in p
    assert "(AI reading of the call, not official text)" in p
    assert "AI-written from their publications" in p
    assert "relevant to Call 1" in p
    assert "Intended research direction: early detection" in p and "Application area: none given" in p
    assert "Researcher data (publications from Scopus and NVA, UiS employee directory) updated: 2026-11-02" in p
    assert out["plain"].startswith("TASK: PROJECT CONCEPTS") and "**" not in out["plain"]


@pytest.mark.skipif(not node_ok(), reason="Node.js 22.18+ needed to run prompt-core.ts")
def test_long_fields_are_shortened_and_large_selections_split(tmp_path):
    long_scope = "Scope sentence. " * 1000          # 16 000 characters
    out = build(tmp_path, base(calls=[call(1, long_scope)], fieldLimit=6000))
    assert out["support"] is None
    assert out["omitted"] == ["Call 1, Scope: shortened from 15999 to 6000 characters"]
    assert "[…shortened; full text: https://funder.example/call-1]" in out["prompt"]

    big = base(calls=[call(k, long_scope) for k in range(1, 6)], researchers=[person(k, 40) for k in range(1, 9)],
               inlineLimit=30000)
    out = build(tmp_path, big)
    assert out["support"] is not None, "a large selection is split into prompt + supporting information"
    assert len(out["prompt"]) < 30000
    assert 'The attached file "supporting information"' in out["prompt"]
    assert "(34 more in the supporting information)" in out["prompt"]
    assert "40. Paper 39" in out["support"] and "Call 5: Call title 5" in out["support"]
