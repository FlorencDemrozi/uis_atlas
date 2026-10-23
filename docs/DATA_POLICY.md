# Data, Licensing and Privacy Policy

These rules are binding for everyone working on the project, including Claude Code.

## 1. Secrets

- API keys (Scopus, Anthropic) live only in `.env`, which is gitignored. Never hard-code them, print them, log them, or commit them.
- If a key is ever exposed (pasted into a chat, committed by mistake), regenerate it at dev.elsevier.com or console.anthropic.com.

## 2. Scopus data (licensed)

Scopus content is licensed to UiS through its subscription. Elsevier’s terms generally do not allow republishing Scopus content to people outside the institution.

| Data | Where it may live |
|---|---|
| Raw API responses, abstracts, full affiliation strings | `data/raw/`, `data/interim/` on the local machine only. **Never in Git, never on the website.** |
| Bibliographic references: title, year, venue, DOI link, Scopus link | Public site |
| Author identifiers: Scopus author ID, ORCID | Public site |
| Derived content: AI-written summaries, topic tags, counts, embedding vectors | Public site, **pending UiS Library confirmation** |

`pipeline/export_public.py` is the single gate between licensed and public data. It must use an explicit **allow-list** of fields; anything not on the list is dropped. A test checks that no abstract text appears in `data/public/`.

Before launch, the UiS Library (which manages the Scopus agreement) must confirm the public field list.

## 3. Personal data (GDPR)

Researcher profiles are personal data, even though they describe professional activity. Before launch:

- Confirm the legal basis and approach with the UiS data protection officer (personvernombud).
- Publish a short privacy notice on the site: what is shown, where it comes from, how often it is updated.
- Provide a way for researchers to **correct or opt out** (for v1: a contact email plus `config/exclusions.json` and `config/overrides.json`, which the pipeline respects).
- The UiS employee directory (`collect_directory.py`) is used to confirm current staff and their unit. The raw copy (`data/raw/uis_directory/`) stays local and is never committed. Only name, position, faculty/department and the UiS profile link may reach the public site, and only for researchers who are in the atlas.
- Summaries describe research only. Never generate personal judgements, rankings of quality, or anything beyond published work.

## 4. AI-generated summaries

- Generated offline with the Claude API from titles, keywords and abstracts.
- Must be written in fresh words, never copying abstract sentences.
- Labelled on the site as automatically generated from publications.
- Spot-checked by the project owner before first launch; researchers can request corrections through the override file.
