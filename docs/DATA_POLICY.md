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
| "Build a team" paper vectors (`team_vectors.py`): made **only from the public title and keywords** in `data/public/papers.json`, never abstracts (project owner, 2026-11-06) | Public site (`team.json`, `team.vectors.bin`). Vectors from abstracts (`embed.py`) stay local. |
| Partner institutions of co-authors outside UiS (`build_partners.py`): Scopus affiliation id, institution name, city, country, and per researcher the number of shared papers | Public site (`partners.json`), **pending UiS Library confirmation**. Institutions only: names or ids of external co-authors are never published. |

`pipeline/export_public.py` is the single gate between licensed and public data. It must use an explicit **allow-list** of fields; anything not on the list is dropped. A test checks that no abstract text appears in `data/public/`.

Before launch, the UiS Library (which manages the Scopus agreement) must confirm the public field list.

## 2b. NVA data (open)

NVA (Nasjonalt vitenarkiv, run by Sikt) publishes its metadata openly through a public API; no key or licence is needed. Raw records stay in `data/raw/nva/` (local, never committed), like all raw data.

| Data | Where it may live |
|---|---|
| Bibliographic references: title, year, venue, type, DOI, link to the NVA record | Public site |
| Cristin person id (link to the NVA research profile) | Public site |
| Abstracts (copyright may lie with the publisher) | Local only, as for Scopus: used for summaries and embeddings, never published |

## 3. Personal data (GDPR)

Researcher profiles are personal data, even though they describe professional activity. Before launch:

- Confirm the legal basis and approach with the UiS data protection officer (personvernombud).
- Publish a short privacy notice on the site: what is shown, where it comes from, how often it is updated. Done as the page "Privacy and cookies" (`#/privacy`, `web/src/views/Privacy.tsx`, texts `priv.*`), linked from the footer. Keep it in step with §3a.

## 3a. Visitors: no cookies, no tracking, no third parties

- The site sets **no cookies** and uses no analytics. Browser storage (`localStorage`, `sessionStorage`, the cache) holds only what is strictly necessary for a function the visitor uses (ekomloven § 3-15): language, theme, shortlist, Project builder, project ideas, the date of the last "What's new" update seen, the funding key for the open tab, and the language model. Nothing of it is sent anywhere. Adding anything else (statistics, embedded videos, external maps or fonts) needs consent and a cookie banner: ask the project owner first, and update the privacy page.
- The visitor's browser contacts **only the Atlas server**. The language model and the ONNX runtime are fetched at build time (`web/scripts/fetch-model.mjs`) and served from the site; the Content-Security-Policy (`deploy/nginx.conf.template`, `connect-src 'self'`) enforces this. Do not load scripts, fonts, models or data from other hosts.
- "What's new" (`pipeline/build_changes.py`): the public `changes.json` holds profile ids and dates only; new calls go into the encrypted funding index. The first-seen state with e-mail addresses as identity keys (`data/interim/first_seen.json`) stays local.
- Provide a way for researchers to **correct or opt out** (for v1: a contact email plus `config/exclusions.json` and `config/overrides.json`, which the pipeline respects).
- The UiS employee directory (`collect_directory.py`) is used to confirm current staff and their unit. The raw copy (`data/raw/uis_directory/`) stays local and is never committed. Only name, position, faculty/department, the UiS profile link and the work e-mail address (as shown on the person's public UiS profile page; decided by the project owner, 2026-11-04) may reach the public site, and only for researchers who are in the atlas.
- Cristin person records (`collect_cristin.py`, open NVA API) are read only for researchers the employee directory does not confirm, to see whether their UiS affiliation is still active. Only the UiS affiliations (unit, active or not, role title) are kept, in `data/raw/cristin_persons.json` (local, never committed). The public site shows the resulting staff status (`staff`: current, former or unknown) and, for current staff found only in Cristin, the role title and unit.
- Summaries describe research only. Never generate personal judgements, rankings of quality, or anything beyond published work.

## 4. AI-generated summaries

- Generated offline with the Claude API from titles, keywords and abstracts.
- Must be written in fresh words, never copying abstract sentences.
- Labelled on the site as automatically generated from publications.
- Spot-checked by the project owner before first launch; researchers can request corrections through the override file.

## 4b. Project ideas (Project builder)

- Generated offline by `pipeline/project_ideas.py` with the Claude API from the call texts, the selected researchers' public profile data, publication titles and keywords, and abstract excerpts of a few publications (as for the summaries in §4), plus the user's preferences.
- The result is a file that stays with the user and is imported into their own browser; nothing is published on the site. Ideas are labelled as AI-generated drafts, never say that anyone has agreed to take part, and are checked against the researchers' listed publications and the call text (see SPEC §5.6).

## 5. Funding calls (docs/FUNDING.md)

- Source: public call pages of the Research Council of Norway, collected politely (robots.txt respected; call PDFs under `*/Download` are not fetched). Raw pages stay in `data/raw/rcn/`.
- Call facts are shown with their source page and location; nothing is filled in by guesswork. AI readings of a call are labelled and checked against quotes from the call.
- Matches and collaborator suggestions describe published work only. They are not an assessment of a person's quality, and never say that someone has agreed to take part.
- `data/public/funding.enc.json` is encrypted with `ATLAS_FUNDING_PASSWORD` (in `.env`, never committed or printed). Its plain content is checked by `export_funding.py` for licensed fields before encryption; it holds paper ids, not abstracts.
- Only researchers who appear on the public site are matched (exclusions and opt-outs apply). External (non-UiS) researchers are not included.
