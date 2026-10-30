#!/usr/bin/env python3
"""
Which open calls fit a project idea? Local tool for the research office.

  python pipeline/idea_match.py "wearable sensors to detect early falls in elderly care"
  python pipeline/idea_match.py --file idea.txt --out result.md
  python pipeline/idea_match.py "..." --no-ai          (shortlist only, nothing sent anywhere)

1. Shortlist: the idea is compared with every open call's scope, aspects and
   example directions (call_vectors.py; the same method as the website's idea box).
   The best config.IDEA_MATCH["review"] calls go on.
2. Review: Claude reads each shortlisted call's own text and says whether the idea
   fits (strong / partial / none), why, and quotes the call. Quotes are checked
   against the call text; a fit whose quote cannot be found is lowered to "partial"
   and marked unverified. Calls open to all fields (FRIPRO, ERC, MSCA) are listed
   separately: they accept any topic.

The idea text is sent to the Anthropic API in step 2 (as the call texts are for the
call profiles); use --no-ai for ideas that must not leave this machine. Nothing is
stored. Needs ANTHROPIC_API_KEY for step 2 and call_vectors.py to have run.
"""
import argparse
import json
import sys
from datetime import date

import call_vectors
import config
import embed
import llm
import match_funding
import profile_calls

CFG = config.IDEA_MATCH
FITS = ("strong", "partial", "none")
CALL_CHARS = 2500   # call text per candidate given to Claude

SYSTEM = """You help a university research office find funding calls for a researcher's \
project idea. You get the idea and a numbered list of open calls with their official text.

For every call decide how well the idea could be submitted to it:
- "strong": the call's scope clearly covers the idea's main aim; a proposal built on the \
idea would be in scope without bending it.
- "partial": the idea fits one part of the call, or would fit after a clear reframing \
(say which).
- "none": the call does not cover the idea, even if it shares words or a general field.
Judge only from the call text given. Do not reward shared buzzwords (e.g. "machine \
learning", "resilience") when the call's application area differs from the idea's.
"reason": one or two sentences in English, concrete. "evidence": an exact quote \
(5-40 words, copied character for character) from that call's text that supports a \
strong or partial fit; empty for "none". Return one entry per call, using its number."""


def schema() -> dict:
    item = {"type": "object", "properties": {"n": {"type": "integer"}, "fit": {"type": "string"},
                                             "reason": {"type": "string"}, "evidence": {"type": "string"}},
            "required": ["n", "fit", "reason", "evidence"], "additionalProperties": False}
    return {"type": "object", "properties": {"calls": {"type": "array", "items": item}},
            "required": ["calls"], "additionalProperties": False}


def shortlist(idea: str, n: int) -> list[tuple[float, dict, list]]:
    """[(score, call, closest text [kind, label])] for the n closest open calls."""
    meta, V = call_vectors.load()
    calls = {c["id"]: c for c in json.loads(config.CALLS.read_text(encoding="utf-8"))["calls"]}
    q = embed.encode(embed.load_model(), [idea], config.QUERY_PREFIX)[0]
    texts = {c["id"]: c["texts"] for c in meta["calls"]}
    out = []
    for score, cid, best in call_vectors.score_calls(q, meta, V)[:n]:
        if cid in calls:
            out.append((score, calls[cid], texts[cid][best]))
    return out


def open_field_calls() -> list[dict]:
    calls = json.loads(config.CALLS.read_text(encoding="utf-8"))["calls"]
    return [c for c in calls if c["fields"]["status"]["v"] != "closed" and c["fields"].get("open_field", {}).get("v")
            and not c["fields"].get("institution_level", {}).get("v")]


def title(call: dict) -> str:
    return match_funding.lang_text(call["fields"]["title"]["v"]) or call["id"]


def deadline(call: dict) -> str:
    f = call["fields"]
    today = date.today().isoformat()
    dates = sorted(d[:10] for d in [f.get(k, {}).get("v") for k in ("preliminary_deadline", "deadline",
                                                                     "full_proposal_deadline")] if d)
    ahead = [d for d in dates if d >= today]
    return ahead[0] if ahead else ("rolling" if f.get("rolling", {}).get("v") else "no deadline found")


def url(call: dict) -> str:
    v = call["fields"]["url"]["v"] or {}
    return v.get("en") or v.get("nb") or ""


def review(idea: str, short: list[tuple[float, dict, list]]) -> dict[str, dict]:
    """{call id: {"fit", "reason", "evidence", "verified"}} from Claude, quotes checked."""
    cl = llm.client()
    if cl is None:
        sys.exit("No ANTHROPIC_API_KEY in .env – run with --no-ai for the shortlist only.")
    texts = {c["id"]: profile_calls.call_text(c)[:CALL_CHARS] for _, c, _ in short}
    body = [f"PROJECT IDEA:\n{idea}\n\nCALLS:"]
    for n, (_, c, _) in enumerate(short, 1):
        body.append(f"\n### Call {n}\n{texts[c['id']]}")
    out = llm.ask_json(cl, SYSTEM, "\n".join(body), schema(), effort="medium", max_tokens=16000)
    if not out:
        sys.exit("Claude gave no usable answer – try again, or use --no-ai.")
    result = {}
    for item in out["calls"]:
        if not 1 <= item["n"] <= len(short):
            continue
        cid = short[item["n"] - 1][1]["id"]
        fit = item["fit"] if item["fit"] in FITS else "none"
        verified = bool(item["evidence"]) and profile_calls.norm(item["evidence"]) in profile_calls.norm(texts[cid])
        if fit == "strong" and not verified:
            fit = "partial"   # a strong fit must rest on the call's own words
        result[cid] = {"fit": fit, "reason": item["reason"], "evidence": item["evidence"] if verified else "",
                       "verified": verified}
    return result


def report(idea: str, short, judged: dict | None) -> str:
    lines = [f"# Calls for a project idea ({date.today().isoformat()})", "", f"> {idea}", ""]
    if judged is None:
        lines += ["Shortlist by text similarity only (no AI check). The relevant calls are usually among",
                  "these, mixed with ones that only share words: check each call.", ""]
        for n, (score, c, closest) in enumerate(short, 1):
            lines.append(f"{n}. **{title(c)}** ({c['id']}) – deadline {deadline(c)}  ")
            lines.append(f"   closest: {closest[1]} · similarity {score:.3f} · {url(c)}")
    else:
        for fit, head in (("strong", "## Good fit"), ("partial", "## Partial fit")):
            rows = [(c, judged[c["id"]]) for _, c, _ in short if judged.get(c["id"], {}).get("fit") == fit]
            lines += [head, ""]
            if not rows:
                lines += ["None among the open calls.", ""]
            for c, j in rows:
                lines.append(f"- **{title(c)}** ({c['id']}) – deadline {deadline(c)}  ")
                lines.append(f"  {j['reason']}  ")
                if j["evidence"]:
                    lines.append(f"  The call says: “{j['evidence']}”  ")
                elif fit == "partial" and not j["verified"]:
                    lines.append("  (no quote from the call could be verified)  ")
                lines.append(f"  {url(c)}")
            lines.append("")
        n_none = sum(1 for j in judged.values() if j["fit"] == "none")
        lines += [f"{n_none} of the {len(short)} closest calls were judged not to fit.", ""]
    lines += ["## Open to all research fields", "",
              "These accept any topic; check eligibility and the call's own rules:", ""]
    lines += [f"- {title(c)} ({c['id']}) – deadline {deadline(c)}" for c in open_field_calls()]
    lines += ["", "AI judgements are suggestions from the call texts, not an assessment of the idea.",
              "Check the official call before deciding."]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Find open funding calls for a project idea.")
    ap.add_argument("idea", nargs="?", help="the idea, a few sentences (or use --file)")
    ap.add_argument("--file", help="read the idea from a text file")
    ap.add_argument("--out", help="also write the result to this Markdown file")
    ap.add_argument("--no-ai", action="store_true", help="shortlist only; the idea is not sent anywhere")
    args = ap.parse_args()
    sys.stdout.reconfigure(errors="replace")
    idea = (open(args.file, encoding="utf-8").read() if args.file else args.idea or "").strip()
    if len(idea.split()) < 4:
        sys.exit("Describe the idea in at least a sentence (what, for whom, how).")
    if not config.CALL_VECTORS.exists():
        sys.exit("No call vectors yet – run: python pipeline/call_vectors.py")
    short = shortlist(idea, CFG["shortlist"] if args.no_ai else CFG["review"])
    judged = None if args.no_ai else review(idea, short)
    text = report(idea, short, judged)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")


if __name__ == "__main__":
    main()
