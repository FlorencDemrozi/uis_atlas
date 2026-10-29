"""The field record shared by every funding source (RCN calls, EU topics).

  {"v": value, "s": status, "src": location, "url": source, "ev": evidence,
   "c": confidence, "m": method}
  status:  "explicit" (stated by the funder), "inferred" (derived by a stated rule),
           "not_specified" (the funder does not say) – never guessed
  method:  "metadata" (the funder's structured fields), "section" (the official text
           passage under that heading), "rule" (deterministic inference),
           "manual" (config/funding_overrides.json), "ai" (profile_calls.py)
"""
import re


def field(v, s="explicit", src=None, url=None, ev=None, c="high", m="metadata") -> dict:
    return {"v": v, "s": s, "src": src, "url": url, "ev": ev, "c": c, "m": m}


def missing() -> dict:
    return field(None, "not_specified", c=None, m=None)


def doc_links(secs: list[dict]) -> list[dict]:
    out, seen = [], set()
    for s in secs:
        for link in s["links"]:
            url = link["url"]
            if (not url or url in seen or url.startswith("mailto:") or "/Download" in url
                    or not link["text"]):
                continue
            seen.add(url)
            t = (link["text"] + " " + url).lower()
            kind = ("template" if re.search(r"mal\b|template|skjema", t)
                    else "faq" if re.search(r"faq|spørsmål og svar|questions", t)
                    else "guidelines" if re.search(r"retningslinj|guideline|veiled|guide|krav|regler", t)
                    else "projects" if "prosjektbanken" in t
                    else "other")
            out.append({"text": link["text"], "url": url, "kind": kind, "src": " > ".join(s["path"])})
    return out
