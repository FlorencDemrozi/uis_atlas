"""Project builder: saved funding calls (web/src/builder-core.ts), run with Node."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from test_team import node_ok

ROOT = Path(__file__).resolve().parent.parent
CORE = (ROOT / "web" / "src" / "builder-core.ts").as_uri()

HARNESS = """
import { readFileSync } from "node:fs";
const b = await import(process.argv[2]);
const inp = JSON.parse(readFileSync(0, "utf8"));
const f = inp.fields, g = inp.changed;
let list = b.addCall([], "c1", f, "2026-11-01T10:00:00Z");
const twice = b.addCall(list, "c1", g, "2026-11-02T10:00:00Z");
const out = {
  facts: b.callFacts(f),
  noDuplicate: twice.length === 1 && twice[0].saved === "2026-11-01T10:00:00Z",
  unchanged: b.changedFacts(list[0], f),
  changed: b.changedFacts(list[0], g),
  afterRefresh: b.changedFacts(b.refreshCall(list, "c1", g, "2026-11-03T00:00:00Z")[0], g),
  olderVersion: b.changedFacts({ id: "c1", saved: "x", facts: { status: "open" } }, g),
  parsed: b.parseSaved(inp.raw),
  parsedBad: [b.parseSaved("not json"), b.parseSaved('{"a":1}'), b.parseSaved(null)],
  closed: inp.closedCases.map(([fields, today]) => b.isClosed(fields, today)),
};
process.stdout.write(JSON.stringify(out));
"""


def run(tmp_path, inp: dict) -> dict:
    script = tmp_path / "harness.mjs"
    script.write_text(HARNESS, encoding="utf-8")
    res = subprocess.run([shutil.which("node"), str(script), CORE], input=json.dumps(inp), capture_output=True,
                         text=True, encoding="utf-8", timeout=60)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


@pytest.mark.skipif(not node_ok(), reason="Node.js 22.18+ needed to run builder-core.ts")
def test_saved_calls(tmp_path):
    fields = {"status": {"v": "open"}, "deadline": {"v": "2027-02-01T13:00"}, "max_amount": {"v": 12000000},
              "rolling": {"v": False}, "title": {"v": {"en": "Not stored"}}}
    changed = dict(fields, deadline={"v": "2027-03-01T13:00"}, status={"v": "closed"})
    raw = json.dumps([
        {"id": "a", "saved": "2026-11-01", "facts": {"status": "open", "evil": "<script>", "deadline": 5}},
        {"id": "a", "saved": "2026-11-02", "facts": {}},          # duplicate: dropped
        {"id": "", "saved": "x"}, {"saved": "x"}, "junk", None,  # malformed: dropped
        {"id": "b", "saved": "2026-11-03"},
    ])
    closed_cases = [
        [{"status": {"v": "closed"}}, "2026-11-06"],
        [{"status": {"v": "open"}, "deadline": {"v": "2026-11-01T13:00"}}, "2026-11-06"],
        [{"status": {"v": "open"}, "deadline": {"v": "2026-12-01"}, "preliminary_deadline": {"v": "2026-10-01"}}, "2026-11-06"],
        [{"status": {"v": "open"}, "deadline": {"v": "2026-01-01"}, "rolling": {"v": True}}, "2026-11-06"],
        [{"status": {"v": "planned"}}, "2026-11-06"],
    ]
    out = run(tmp_path, {"fields": fields, "changed": changed, "raw": raw, "closedCases": closed_cases})

    assert out["facts"]["deadline"] == "2027-02-01T13:00" and out["facts"]["max_amount"] == "12000000"
    assert "title" not in out["facts"], "call texts are not stored in the browser"
    assert out["noDuplicate"]
    assert out["unchanged"] == []
    assert out["changed"] == ["status", "deadline"]
    assert out["afterRefresh"] == []
    assert out["olderVersion"] == ["status"]   # only facts that were saved are compared
    assert out["parsed"] == [{"id": "a", "saved": "2026-11-01", "facts": {"status": "open"}},
                             {"id": "b", "saved": "2026-11-03", "facts": {}}]
    assert out["parsedBad"] == [[], [], []]
    assert out["closed"] == [True, True, False, False, False]
