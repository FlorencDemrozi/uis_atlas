"""Short status message about the weekly run, sent to Telegram (run_weekly.py).

Needs TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env (setup: docs/DEPLOY.md);
without them nothing is sent. Standard library only. A message that cannot be sent
is reported in the log but never fails the run. Messages hold counts and stage
names only – no personal data, no keys.
"""
import json
import os
import urllib.parse
import urllib.request

import config

API = "https://api.telegram.org/bot{}/sendMessage"


def configured() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def counts() -> list[str]:
    """One line each about the funding data, from the files the run just wrote."""
    lines = []
    try:
        calls = json.loads(config.CALLS.read_text(encoding="utf-8"))["calls"]
        active = [c for c in calls if c["fields"]["status"]["v"] != "closed"]
        by_src = {s: sum(c["source"] == s for c in active) for s in ("rcn", "eu")}
        lines.append(f"Open/planned calls: {by_src['rcn']} RCN, {by_src['eu']} EU")
    except (OSError, ValueError, KeyError):
        pass
    try:
        matches = json.loads(config.FUNDING_MATCHES.read_text(encoding="utf-8"))["calls"]
        strong = sum(m["category"] != "low" for c in matches.values() for m in c["matches"])
        lines.append(f"Matches: {strong} high/medium in {len(matches)} calls")
    except (OSError, ValueError, KeyError):
        pass
    try:
        lines.append(f"AI call profiles: {len(json.loads(config.CALL_PROFILES.read_text(encoding='utf-8')))}")
    except (OSError, ValueError):
        pass
    return lines


def send(text: str) -> str | None:
    """Sends the message; returns an error text, or None when sent or not configured."""
    if not configured():
        return None
    body = urllib.parse.urlencode({"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text[:4000]}).encode()
    try:
        with urllib.request.urlopen(API.format(os.environ["TELEGRAM_BOT_TOKEN"]), body, timeout=20) as r:
            return None if json.load(r).get("ok") else "Telegram did not accept the message"
    except Exception as exc:  # never let a notification break the run
        # The URL holds the token: report only the kind of error, not the message text.
        return f"Telegram message not sent ({type(exc).__name__})"


if __name__ == "__main__":  # test the setup: python pipeline/notify.py
    if not configured():
        raise SystemExit("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are not both set in .env.")
    problem = send("\n".join(["UiS Atlas: test message – Telegram is set up."] + counts()))
    raise SystemExit(problem or "Sent.")
