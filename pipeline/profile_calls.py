#!/usr/bin/env python3
"""
Stage 3c – Call Intelligence Profiles: what each open or planned call asks for
scientifically, read from the official call text by the Claude API (offline).

Input:  config.CALLS
Output: config.CALL_PROFILES  ({call_id: {"source_hash", "model", "generated", "profile"}})

The profile separates facts from interpretation:
- topics / competencies / fields carry a "basis" or "status" and a verbatim
  "evidence" quote from the call. Quotes are checked against the call text
  before anything is stored; a "fact" whose quote is not found is downgraded to
  an interpretation (topics, competencies) or dropped (fields). Nothing about
  deadlines, amounts or URLs is asked of the model – those come from
  build_calls.py.
- "interpretation" is labelled AI-generated on the site.
Cached by a hash of the call text; closed calls are skipped. Without
ANTHROPIC_API_KEY the stage does nothing and matching uses the call text only.
"""
import hashlib
import json
import re
from datetime import datetime

import config
import llm
from build_calls import AI_ONLY_FIELDS

PROMPT_VERSION = 1

# Text fields the model may also condense (next to the official passage).
CONDENSE_FIELDS = ["funding_rate", "eligible_costs", "funding_restrictions", "eligible_applicants",
                   "pi_requirements", "partner_requirements", "international_rules", "evaluation_criteria"]
AI_FIELDS = AI_ONLY_FIELDS + CONDENSE_FIELDS
KINDS = ["core", "complementary", "mandatory_partner", "optional"]

SYSTEM = """You analyse research funding calls for a university's research office. \
You read one call from the Research Council of Norway and describe, in English, \
what scientific expertise a competitive proposal needs.

Rules:
- Use only the call text given. Never invent requirements, partners, amounts or dates.
- Every item marked "explicit" (topics) or with status "explicit" (fields) must have \
an "evidence" field that is an exact quote (5–40 words, copied character for \
character, in the call's language) from the call text.
- Items that are your reasonable reading of the call but not stated are \
"interpretation" (topics) or status "inferred" (fields), still with the closest \
supporting quote when there is one, else an empty string.
- If the call does not say something, use status "not_specified" and value "".
- Topics are hierarchical paths from broad discipline to specific topic, e.g. \
["Biomedical engineering", "Physiological monitoring", "Wearable sensing"]. Do not \
add technologies the call's objectives do not support.
- Competencies: "core" = directly needed for the scientific objectives; \
"complementary" = would improve the project; "mandatory_partner" = required by \
the call's conditions (e.g. a company or user partner); "optional" = useful, not essential.
- Field values are short (one or two sentences) and factual."""

STR = {"type": "string"}
LIST = {"type": "array", "items": STR}


def schema() -> dict:
    obj = lambda props: {"type": "object", "properties": props, "required": list(props),
                         "additionalProperties": False}
    field = obj({"value": STR, "status": {"type": "string", "enum": ["explicit", "inferred", "not_specified"]},
                 "evidence": STR})
    return obj({
        "disciplines": {"type": "array", "items": obj({
            "path": LIST, "level": {"type": "string", "enum": ["primary", "secondary"]}})},
        "topics": {"type": "array", "items": obj({
            "path": LIST, "basis": {"type": "string", "enum": ["explicit", "interpretation"]}, "evidence": STR})},
        "objectives": LIST, "challenges": LIST, "methods": LIST, "technologies": LIST,
        "application_domains": LIST, "expected_contributions": LIST, "interdisciplinary": LIST,
        "competencies": {"type": "array", "items": obj({
            "name": STR, "kind": {"type": "string", "enum": KINDS}, "rationale": STR, "evidence": STR})},
        "interpretation": obj({
            "problems": STR, "suitable_projects": STR, "competitive_teams": STR,
            "explicit_directions": LIST, "plausible_directions": LIST}),
        "fields": obj({k: field for k in AI_FIELDS}),
    })


def call_text(call: dict) -> str:
    f = call["fields"]
    lang = "en" if call["sections"]["en"] else "nb"
    title = f["title"]["v"].get(lang) or f["title"]["v"]["nb"]
    lines = [f"Title: {title}"]
    if f["summary"]["v"]:
        lines.append(f"Summary: {f['summary']['v'].get(lang) or f['summary']['v'].get('nb')}")
    for key in ("scheme", "programme", "themes", "target_groups"):
        v = f[key]["v"]
        if v:
            v = v.get(lang) or v.get("nb")
            lines.append(f"{key.replace('_', ' ').title()}: {', '.join(v) if isinstance(v, list) else v}")
    for s in call["sections"][lang]:
        lines.append(f"\n## {' > '.join(s['path'])}\n{s['text']}")
    return "\n".join(lines)


def norm(s: str) -> str:
    return re.sub(r"\W+", " ", s.lower()).strip()


def verify(profile: dict, source: str) -> dict:
    """Check every quote against the call text; downgrade or drop what does not check out."""
    src = norm(source)
    found = lambda q: bool(q) and len(norm(q).split()) >= 3 and norm(q) in src
    for t in profile["topics"]:
        if t["basis"] == "explicit" and not found(t["evidence"]):
            t["basis"], t["evidence"] = "interpretation", ""
    for c in profile["competencies"]:
        c["verified"] = found(c["evidence"])
        if not c["verified"]:
            c["evidence"] = ""
    for key, fv in list(profile["fields"].items()):
        if fv["status"] == "not_specified" or not fv["value"].strip():
            profile["fields"][key] = {"value": "", "status": "not_specified", "evidence": ""}
        elif not found(fv["evidence"]):
            if fv["status"] == "explicit":  # a fact we cannot trace is not stored
                profile["fields"][key] = {"value": "", "status": "not_specified", "evidence": ""}
            else:
                fv["evidence"] = ""
    return profile


def main() -> None:
    cl = llm.client()
    if cl is None:
        print("No ANTHROPIC_API_KEY in .env – call profiles skipped (matching uses the call text).")
        return
    calls = json.loads(config.CALLS.read_text(encoding="utf-8"))["calls"]
    cache = json.loads(config.CALL_PROFILES.read_text(encoding="utf-8")) if config.CALL_PROFILES.exists() else {}
    todo = [c for c in calls if c["fields"]["status"]["v"] != "closed"]
    made = 0
    for i, call in enumerate(todo, 1):
        text = call_text(call)
        h = hashlib.sha256(f"{config.SUMMARY_MODEL}|{PROMPT_VERSION}|{text}".encode()).hexdigest()
        if cache.get(call["id"], {}).get("source_hash") == h:
            continue
        out = llm.ask_json(cl, SYSTEM, text, schema(), effort="medium", max_tokens=16000)
        if not out:
            print(f"  [{i}/{len(todo)}] {call['id']}: no usable answer (kept previous profile, if any)")
            continue
        cache[call["id"]] = {"source_hash": h, "model": config.SUMMARY_MODEL,
                             "generated": datetime.now().isoformat(timespec="seconds"),
                             "profile": verify(out, text)}
        config.CALL_PROFILES.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
        made += 1
        print(f"  [{i}/{len(todo)}] {call['id']}")
    print(f"Call profiles: {made} new or updated, {len(todo) - made} unchanged or failed.")


if __name__ == "__main__":
    main()
