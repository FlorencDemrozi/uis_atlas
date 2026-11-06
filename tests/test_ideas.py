"""Project builder, project ideas: the generator's checks (pipeline/project_ideas.py, no API)
and the site's file handling, rendering and Word export (web/src/ideas-core.ts, docx.ts)."""
import base64
import io
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import pytest

from test_team import node_ok

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import project_ideas  # noqa: E402

CALL_TEXT = ("Proposals should develop predictive biomarkers of disease progression. "
             "Applicants must involve at least three independent legal entities from different Member States.")
TEAM = [{"scopus_id": "a1", "name": "Ada One"}, {"scopus_id": "b2", "name": "Bo Two"}]
REFS = {"R1-P1": {"eid": "e1", "title": "Wearable gait sensing", "year": "2025", "link": ""},
        "R1-profile": {"text": "works on wearables"},
        "R2-P1": {"eid": "e2", "title": "Parkinson cohort", "year": "2024", "link": ""}}


def answer(**kw) -> dict:
    a = {"fit": "good", "fit_reason": "Covers it.", "missing_expertise": ["Regulatory science"], "offer_concept": True,
         "concept": {
             "title": "Digital biomarkers", "acronym": "DIGI", "problem": "p", "approach": "a", "beneficiaries": "b",
             "call_fit": [{"element": "Scope", "how": "h", "quote": "develop predictive biomarkers of disease progression"},
                          {"element": "Impact", "how": "h", "quote": "a sentence the call never had"}],
             "objectives": ["o"], "innovation": "i", "needs_validation": ["v"],
             "roles": [{"researcher": 1, "role": "AI lead", "evidence": [{"ref": "R1-P1", "note": "gait"},
                                                                          {"ref": "R1-profile", "note": "wearables"},
                                                                          {"ref": "R2-P1", "note": "not hers"}]},
                       {"researcher": 2, "role": "Clinical lead", "evidence": [{"ref": "R2-P9", "note": "invented"}]},
                       {"researcher": 7, "role": "Ghost", "evidence": []}],
             "work_packages": [{"name": "WP", "activities": ["x"], "deliverables": ["d"], "lead": "R2"},
                               {"name": "WP2", "activities": [], "deliverables": [], "lead": "SME partner"}],
             "outcomes": ["out"], "impact": "imp", "partners": [{"kind": "clinical", "why": "trials"}],
             "feasibility": {"consortium": "c", "duration": "36 months", "budget": "b", "trl": "4-6", "eligibility": [
                 {"item": "Consortium", "status": "stated",
                  "quote": "at least three independent legal entities from different Member States", "note": ""},
                 {"item": "Norway", "status": "stated", "quote": "Norway is fully eligible in all cases", "note": ""}]},
             "assumptions": ["A hospital joins"]}}
    a.update(kw)
    return a


def test_generator_checks_the_answer():
    out = project_ideas.check(answer(), {}, CALL_TEXT, TEAM, REFS, ["An abstract about something else entirely."])
    c = out["concept"]
    assert [r["name"] for r in c["roles"]] == ["Ada One", "Bo Two"], "a role for an unknown researcher is dropped"
    ev = c["roles"][0]["evidence"]
    assert [e["verified"] for e in ev] == [True, True, False], "evidence must cite that researcher's own items"
    assert "Wearable gait sensing" in ev[0]["text"]
    assert c["roles"][1]["evidence"][0]["verified"] is False   # R2-P9 was never shown
    assert [x["verified"] for x in c["call_fit"]] == [True, False]
    assert [e["status"] for e in c["feasibility"]["eligibility"]] == ["stated", "unverified"]
    assert [w["lead"] for w in c["work_packages"]] == ["Bo Two", "SME partner"]
    assert out["cited"] == ["e1"]
    assert any("unknown researcher" in w for w in out["warnings"])
    assert any("could not be found in the call text" in w for w in out["warnings"])


def test_poor_fit_never_gets_a_concept():
    out = project_ideas.check(answer(fit="poor", offer_concept=True), {}, CALL_TEXT, TEAM, REFS, [])
    assert out["concept"] is None and out["missing_expertise"] == ["Regulatory science"]
    assert project_ideas.check(answer(fit="partial", offer_concept=False), {}, CALL_TEXT, TEAM, REFS, [])["concept"] is None


def test_copied_abstract_text_is_flagged():
    abstract = "We present a new method that combines inertial sensors and deep learning to detect freezing of gait episodes at home"
    a = answer()
    a["concept"]["approach"] = "Approach: " + abstract
    out = project_ideas.check(a, {}, CALL_TEXT, TEAM, REFS, [abstract])
    assert any("abstract word for word" in w for w in out["warnings"])


def test_selection_file_is_validated(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"format": "something else"}', encoding="utf-8")
    with pytest.raises(SystemExit):
        project_ideas.load_selection(bad)
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"format": "uis-atlas-selection", "version": 1, "researchers": ["a"], "calls": []}),
                     encoding="utf-8")
    with pytest.raises(SystemExit):
        project_ideas.load_selection(empty)
    ok = tmp_path / "ok.json"
    ok.write_text(json.dumps({"format": "uis-atlas-selection", "version": 1, "researchers": ["a", "a", 5],
                              "calls": [{"id": "c1", "facts": {"status": "open"}}, {"x": 1}],
                              "prefs": {"direction": "d"}, "answer_language": "English"}), encoding="utf-8")
    sel = project_ideas.load_selection(ok)
    assert sel["researchers"] == ["a"] and [c["id"] for c in sel["calls"]] == ["c1"]
    assert sel["prefs"] == {"direction": "d", "area": "", "constraints": ""}


# ---------------------------------------------------------------- the site (Node)
HARNESS = """
import { readFileSync } from "node:fs";
const core = await import(process.argv[2]);
const docx = await import(process.argv[3]);
const inp = JSON.parse(readFileSync(0, "utf8"));
const out = {};
const errors = [];
for (const bad of inp.bad) { try { core.parseIdeasFile(bad); errors.push("accepted"); } catch (e) { errors.push(e.message); } }
out.errors = errors;
const ideas = core.parseIdeasFile(inp.file);
out.ids = ideas.map((i) => i.id);
out.first = ideas[0];
out.merged = core.mergeIdeas([{ ...ideas[1], fit_reason: "old" }, { ...ideas[0], id: "kept" }], [ideas[1]]).map((i) => [i.id, i.fit_reason]);
const blocks = ideas.map((i) => core.ideaBlocks(i, inp.labels));
out.md = blocks.map((b) => core.blocksToMarkdown(b));
out.docx = Buffer.from(docx.blocksToDocx(blocks[0], "DIGI: Digital biomarkers", "2026-11-06T14:05:00.123Z")).toString("base64");
out.selection = core.makeSelection(["a", "a", "b"], [{ id: "c", facts: {} }, { id: "c", facts: {} }],
  { direction: "", area: "", constraints: "" }, "English", { atlas: "2026-11-02", funding: "2026-11-03" }, "now");
process.stdout.write(JSON.stringify(out));
"""

LABELS = {k: k.upper() for k in [
    "draft", "call", "deadline", "researchers", "generated", "dataDates", "fit", "fitGood", "fitPartial", "fitPoor",
    "mismatch", "missingExpertise", "summary", "problem", "approach", "beneficiaries", "callFit", "quote", "unverified",
    "objectives", "innovation", "needsValidation", "roles", "evidence", "workPackages", "activities", "deliverables",
    "lead", "outcomes", "impact", "partners", "feasibility", "consortium", "duration", "budget", "trl", "eligibility",
    "stated", "assumptions", "sources", "warnings", "preferences", "notChecked"]}


def ideas_file() -> str:
    res = project_ideas.check(answer(), {}, CALL_TEXT, TEAM, REFS, [])
    res.pop("cited")
    res["concept"]["sources"] = [{"label": "Call", "url": "https://funder.example/c1"},
                                 {"label": "Bad link", "url": "javascript:alert(1)"}]
    res["concept"]["title"] = "Digital <biomarkers> & “quotes”"
    common = {"call": {"id": "c1", "title": "Call one", "url": "https://funder.example/c1", "funder": "EU",
                       "deadline": "2027-02-01", "facts": {"status": "open"}},
              "researchers": [{"id": "a1", "name": "Ada One", "unit": "Dept", "profile": "https://atlas/#/r/a1"}]}
    poor = {"fit": "poor", "fit_reason": "Not covered.", "missing_expertise": ["Pharmacology"], "concept": None, "warnings": []}
    return json.dumps({"format": "uis-atlas-project-ideas", "version": 1, "generated": "2026-11-06T14:05:00",
                       "model": "m", "prefs": {"direction": "d", "area": "", "constraints": ""}, "answer_language": "English",
                       "data_dates": {"atlas": "2026-11-02", "funding": "2026-11-03", "calls": "2026-11-03"},
                       "ideas": [{"id": "t-c1", **common, **res}, {"id": "t-c2", **common, **poor}, {"no": "id"}]})


@pytest.mark.skipif(not node_ok(), reason="Node.js 22.18+ needed to run ideas-core.ts and docx.ts")
def test_site_reads_renders_and_exports_ideas(tmp_path):
    script = tmp_path / "harness.mjs"
    script.write_text(HARNESS, encoding="utf-8")
    inp = {"file": ideas_file(), "labels": LABELS,
           "bad": ["not json", '{"format": "uis-atlas-selection"}', '{"format": "uis-atlas-project-ideas", "version": 2}',
                   '{"format": "uis-atlas-project-ideas", "version": 1, "ideas": []}']}
    src = ROOT / "web" / "src"
    res = subprocess.run([shutil.which("node"), str(script), (src / "ideas-core.ts").as_uri(), (src / "docx.ts").as_uri()],
                         input=json.dumps(inp), capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)

    assert out["errors"] == ["not JSON", "not a project ideas file", "unsupported version 2", "no ideas in the file"]
    assert out["ids"] == ["t-c1", "t-c2"], "an entry without an id is dropped"
    first = out["first"]
    assert first["generated"] == "2026-11-06T14:05:00" and first["data_dates"]["calls"] == "2026-11-03"
    assert [s["url"] for s in first["concept"]["sources"]] == ["https://funder.example/c1"], "non-web links are dropped"
    assert out["merged"] == [["t-c2", "Not covered."], ["kept", "Covers it."]]
    assert out["selection"]["researchers"] == ["a", "b"] and len(out["selection"]["calls"]) == 1

    md, md_poor = out["md"]
    assert md.startswith("# DIGI: Digital <biomarkers> & “quotes”\n\n> DRAFT")
    for part in ("## FIT: FITGOOD", "### Ada One: AI lead", "EVIDENCE: gait – “Wearable gait sensing” (2025)",
                 "(UNVERIFIED)", "WP1: WP – LEAD: Bo Two", "Consortium: STATED", "Norway: UNVERIFIED",
                 "## ASSUMPTIONS\n\n- A hospital joins", "## WARNINGS"):
        assert part in md, part
    assert "## SUMMARY" not in md_poor and "> MISMATCH" in md_poor and "- Pharmacology" in md_poor

    z = zipfile.ZipFile(io.BytesIO(base64.b64decode(out["docx"])))
    assert z.testzip() is None
    assert {"[Content_Types].xml", "_rels/.rels", "word/document.xml", "word/styles.xml",
            "word/_rels/document.xml.rels", "docProps/core.xml"} <= set(z.namelist())
    for name in z.namelist():
        ElementTree.fromstring(z.read(name))          # every part is well-formed XML
    doc = z.read("word/document.xml").decode("utf-8")
    assert 'w:val="Title"' in doc and 'w:val="Heading1"' in doc
    assert "Digital &lt;biomarkers&gt; &amp; “quotes”" in doc
    assert "Wearable gait sensing" in doc


def test_researcher_numbers_become_names():
    a = answer(fit_reason="R1 brings sensors and R2 the cohort; R9 is unknown.")
    a["concept"]["approach"] = "R2 leads the cohort work."
    out = project_ideas.check(a, {}, CALL_TEXT, TEAM, REFS, [])
    assert out["fit_reason"] == "Ada One brings sensors and Bo Two the cohort; R9 is unknown."
    assert out["concept"]["approach"] == "Bo Two leads the cohort work."
    assert project_ideas.check(answer(fit="poor", fit_reason="R1 only."), {}, CALL_TEXT, TEAM, REFS, [])["fit_reason"] == "Ada One only."
