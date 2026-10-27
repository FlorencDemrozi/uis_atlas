"""Shared Claude API helper for the offline pipeline stages (researcher summaries,
funding call profiles). Runs only on the machine that runs the pipeline; the key
comes from .env via config and never reaches the website.

Every answer is constrained to a JSON schema (structured outputs) and then checked
again by the caller before it is stored.
"""
import json

import config

# Server-side fallback: if the model declines a request, the API retries it on a
# suitable model inside the same call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def client():
    """An Anthropic client, or None when no key is configured (stages then skip)."""
    if not config.ANTHROPIC_API_KEY:
        return None
    import anthropic
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, max_retries=5)


def ask_json(cl, system: str, user: str, schema: dict, effort: str = "low",
             max_tokens: int = 8000) -> dict | None:
    """One request, answer parsed as JSON. None if the model declined or ran out of room."""
    resp = cl.beta.messages.create(
        model=config.SUMMARY_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        betas=[FALLBACK_BETA],
        fallbacks="default",
    )
    if resp.stop_reason in ("refusal", "max_tokens"):
        return None
    text = next((b.text for b in resp.content if b.type == "text"), None)
    return json.loads(text) if text else None
