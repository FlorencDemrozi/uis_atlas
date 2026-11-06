# UiS Researcher Atlas — Project Specification

## 1. Purpose

The UiS Researcher Atlas is a public, searchable dashboard of researchers at the **six faculties of the University of Stavanger (UiS)**. Its job is to help people find the right UiS researcher to collaborate with.

A visitor describes, in their own words, what they are looking for — for example *“machine learning for predictive maintenance of offshore wind turbines”* or *“CO₂ storage in North Sea reservoirs”*. The atlas returns a list of researchers **ranked by affinity** to that description, each with a short overview of who they are and why they matched.

### Users

| User | Typical need |
|---|---|
| UiS employees | Find internal collaborators across departments for proposals (NFR, Horizon Europe), co-supervision, teaching |
| External partners (industry, public sector, other universities) | Find the right UiS contact for a project, a problem or an expert opinion |
| UiS leadership / research administration | Overview of research strengths and activity per department |

Visitors are not expected to know UiS’s organisation or academic vocabulary. The search must work for plain-language and for technical queries, in **English and Norwegian**.

## 2. Scope (version 1)

- **Units:** all six faculties and their departments (as of 23/10/2026, confirmed by the project owner; defined in `pipeline/config.py` `FACULTIES`):
  - Faculty of Science and Technology: Mathematics and Physics; Electrical Engineering and Computer Science; Safety, Economics and Planning; Energy and Petroleum Engineering (incl. former Energy Resources); Chemistry, Bioscience and Environmental Engineering; Mechanical and Structural Engineering and Materials Science
  - Faculty of Arts and Education: Education and Sports Science; Cultural Studies and Languages; Early Childhood Education
  - Faculty of Performing Arts: Jazz, Dance, Practical-Pedagogical Education and Music Production; Classical Music
  - UiS School of Business and Law: Economics and Finance; Innovation, Management and Marketing; Accounting and Law
  - Faculty of Health Sciences: Public Health; Quality and Health Technology; Caring and Ethics
  - Faculty of Social Sciences: Media and Social Sciences; Social Studies; Psychology; NHS – Leadership and Service Innovation (assigned from Scopus affiliations only; not a unit in the employee directory)
  - Not included: national centres (Reading Centre, Learning Environment Centre, Knowledge Centre for Education), the Museum of Archaeology, central divisions.
- **Current staff and departments:** the public UiS employee directory (www.uis.no/nb/sok/ansatte) is the source of who works where today; Scopus affiliations are the fallback.
- **Inclusion:** everyone found in the directory who has a Scopus profile or NVA registrations, whatever their publication record (project owner, 2026-10-28 and 2026-11-02); others (who may have left UiS) with ≥3 publications with a UiS affiliation in the last 2 years (`config.py`; lectures, media items and errata do not count). Staff with neither will come from a staff list (Excel, with start and contract dates) later.
- **Period:** publications from 2020 onward (configurable via `ATLAS_FIRST_YEAR`).
- **Sources:** Scopus (Elsevier), UiS affiliation ID `60014497`, via the Scopus API; and NVA (Nasjonalt vitenarkiv, Sikt; the successor of Cristin), UiS organisation `217.0.0.0`, via its open API (added 2026-11-02). NVA adds books, chapters, reports, Norwegian-language articles, artistic work, lectures and media contributions that Scopus does not index. An output in both sources counts once (same DOI, else same title and year).
- **Output types:** profiles show counts for every category (project owner, 2026-11-02; `config.OUTPUT_CATEGORIES`). "Publications" (headline count, papers per year, unit statistics) are journal articles, books, chapters, conference papers, reports and PhD theses. Student theses are not collected.
- Faculties and departments are configuration (`pipeline/config.py`, `web/src/org.ts`), not code.
- Known limitation: Scopus covers humanities, law and especially performing arts poorly; NVA (since 2026-11-02) fills much of that gap. NVA has no citation counts, so citations still come from Scopus only.

Out of scope for v1: login, editing by researchers through the site, patents.

**Funding calls (added 2026-10-26, project owner):** open and planned calls from the Research Council of Norway, matched with researchers' publications from the last 5 years, with internal collaborator suggestions. Password protected. See `docs/FUNDING.md`. Deferred: external collaborators, suggested teams, other funders.

## 3. Architecture

The project has two halves: an **offline Python pipeline** run locally by the project owner, and a **static website** with no server and no secrets.

```
 Scopus API ──► collect ──► build profiles ──► summarize ──► embed ──► export public
 (UiS network)   raw/        interim/          interim/      interim/    data/public/
                                                                            │
                                                         web/ (static site) ◄┘
                                                         search runs in the browser
```

Why static: it can be hosted anywhere (GitHub Pages, UiS web server), costs nothing to run, never exposes API keys, and has no server to maintain.

### 3.1 Pipeline stages (`pipeline/`)

| Stage | Script | Input → Output | Notes |
|---|---|---|---|
| 1. Collect | `collect_scopus.py` | Scopus API → `data/raw/scopus/` | **Already implemented.** Resumable. Must run on the UiS network or with an institutional token. |
| 1f. NVA | `collect_nva.py` | NVA search API → `data/raw/nva/` | UiS outputs per publication year, any network, no key; resumable by year, recent years refreshed. |
| 1b. Directory | `collect_directory.py` | UiS employee directory → `data/raw/uis_directory/` | Current staff, unit, position, profile link (nb + en). Any network; polite (~100 requests). |
| 2. Build profiles | `build_profiles.py` | raw → `data/interim/profiles.json`, `papers.json` | One record per researcher: department, papers, output types, keywords, co-authors, metrics. Merges Scopus and NVA (`nva.py`): shared outputs once, NVA people linked to Scopus authors by shared papers and the employee directory. Handles name variants and duplicate Scopus author IDs. People found only in NVA get the profile id `nva-<Cristin id>`. |
| 3. Summarize | `summarize.py` | profiles → `data/interim/summaries.json` | Uses the Claude API **offline** to write a 2–3 sentence overview and 3–6 topic tags per researcher. Cached and only regenerated when a profile changes. |
| 4. Embed | `embed.py` | profiles + summaries → `data/interim/embeddings.npy` | Semantic vectors for each researcher and for each paper (see §4). |
| 5. Export | `export_public.py` | interim → `data/public/` | Writes **only licence-safe fields** (see `DATA_POLICY.md`). This is the only data the website sees. |
| 5b. Team vectors | `team_vectors.py` | `data/public/papers.json` → `data/public/team.json`, `team.vectors.bin` | "Build a team" (§5.5): vectors of the **public** title + keywords of recent papers (int8, ~6 MB), cached by text. Never abstracts. |

Each stage is a standalone script that can be rerun independently. `pipeline/run_all.py` runs stages 2–5. Stage 1 is run separately because it needs the UiS network.

### 3.2 Website (`web/`)

- Static single-page app built with **Vite + TypeScript**. Use a small framework (Preact or Svelte) if it simplifies the code, not React with heavy dependencies.
- Loads `data/public/*.json` and embedding vectors at start-up.
- All search and ranking happens **in the browser**.
- Deployable as plain files.

## 4. Affinity ranking

The core feature. The goal is that the top 5 results for a reasonable query are people a domain expert would agree are relevant.

### 4.1 Method: hybrid semantic + keyword search

1. **Semantic score.** Use the multilingual embedding model `intfloat/multilingual-e5-small`. It handles Norwegian and English queries against English publications.
   - Offline (Python, `sentence-transformers`): embed each paper as `"passage: " + title + keywords + abstract`, and each researcher’s summary.
   - In the browser (`@huggingface/transformers`, model `Xenova/multilingual-e5-small`): embed the query as `"query: " + text`.
   - Researcher semantic score = weighted combination of the best-matching papers (for example, the mean of the top 3 paper similarities) and the similarity to the researcher’s summary. A person with several relevant papers should outrank someone with one lucky hit.
   - **The same model and prefixes must be used offline and in the browser.** Add a test that checks this.
2. **Keyword score.** BM25 over titles, keywords and topic tags (e.g. MiniSearch in the browser). This catches exact terms, acronyms and names (“CCS”, “LiDAR”, “FPSO”).
   Query syntax: `"exact phrase"` (words adjacent and in order within one field; case and punctuation ignored), and `AND` / `OR` in capitals, AND binding tighter (`a AND b OR c` = `(a AND b) OR c`). Plain words without quotes or operators behave as before (any word may match, more matches rank higher).
3. **Final score.** `0.7 × semantic + 0.3 × keyword`, both normalised to 0–1, plus a small recency boost for recent relevant work. Keep the weights in one config object so they can be tuned.

### 4.2 Explaining matches

Each result must show **why** the person matched: the 2–3 papers that contributed most, and the matched topic tags. Users trust a ranking they can check.

### 4.3 Evaluation

Create `tests/search_eval.json` with 15–20 realistic queries and the researchers the project owner considers correct answers. Report top-5 hit rate when weights or models change. Ask the project owner to supply or confirm the expected answers.

## 5. Website features

### 5.1 Search (main view)
- One large free-text search field as the first thing on the page, with 3–4 example queries the user can click.
- Results list ordered by affinity, each showing:
  - Name, position (if available), department
  - 2–3 sentence overview
  - Topic tags
  - “Why this match”: the most relevant papers (title, year, venue, link via DOI)
  - Number of publications in the period, main collaborating departments
  - Links: UiS profile, Cristin, ORCID, Scopus author page
- Filters: faculties and departments (any combination: faculty chips for one click, a grouped checklist for single departments; the choice applies to all views and is kept in the URL as `?org=`), minimum number of publications.
- Shareable search URLs (the query encoded in the link).

### 5.2 Researcher profile
A detail view for one researcher: full overview, all topic tags, publication list (titles, links), frequent UiS co-authors (linking to their profiles), publications per year.

### 5.3 Overview
A dashboard page for the selected faculties/departments (grouped by faculty when several faculties are selected, else by department) with: researchers and publications per unit, publications per year, main research themes per department, and a collaboration network between departments (and optionally between researchers).

### 5.5 Find a team (2026-11-06; first called "Build a team")
Someone describes a project in a few sentences (e.g. a proposal abstract) and gets UiS
researchers who **together** cover its parts. A section of the Project builder (§5.6,
`#/builder`; the old address `#/team` still works), public; linked from the
search page (a hint when a query is 15 words or longer) and the Funding idea box. The
description is handed over within the browser tab (sessionStorage), never in the URL.

- **Aspects.** The text is split by rule (`team.split_aspects`): the whole description,
  each sentence, and the things a sentence lists ("such as dementia or Parkinson's
  disease"; "wearables, environmental sensors, gamified tasks and …"). Shown as chips the
  visitor can remove, and own aspects can be added; results update at once.
- **Score.** Each aspect is embedded in the browser ("query:") and compared with the
  title + keyword vectors of every paper since `ACTIVE_FROM`. Relevance per paper is 0 at
  the aspect's floor (its top 0.5 % paper, at least 0.825) and 1 at floor + 0.03, so short
  and long aspects are treated alike. A person's aspect score is the mean relevance of
  their **2** best papers. A listed item counts in the context of its sentence: people who
  do not match that sentence keep 30 % of their score ("agitation" in a dementia-care
  sentence should not find chemists).
- **Team.** Greedy coverage (`team.build_team`): repeatedly add the eligible person who
  adds most above what the team already covers (at least 0.3), up to 6; co-authors of the
  team (×1.15) and new departments (×1.05) are preferred when gains are close. Also shown:
  the 5 best people per aspect with the papers behind each match, and **gaps** (aspects
  nobody covers: a case for an external partner). The faculty/department picker limits
  who is considered.
- **One method, two places.** `pipeline/team.py` and `web/src/team-core.ts` are mirrors;
  `tests/test_team.py` runs both on the same inputs (Node) and checks they agree. Settings:
  `config.TEAM_MATCH`, copied into `team.json`.
- **AI-checked version (local).** `python pipeline/team_match.py "description"`: Claude
  lists the expertise the project needs (4–10 aspects), matching uses the local vectors
  (with abstracts), and Claude judges the 6 best people per aspect from their numbered
  paper titles and summary (strong / partial / none, citing a paper number; a strong fit
  without a valid citation is lowered to partial). Team and gaps from the judgements.
  Sends the description, paper titles/keywords and public summaries (no abstracts) to the
  Anthropic API, a few US cents per run; `--no-ai` sends nothing, `--source public`
  reproduces the website exactly.
- **Evaluation (2026-11-06).** Five abstracts (digital biomarkers in dementia/Parkinson's,
  offshore wind digital twin + hydrogen, generative AI in schools, EU sustainable finance,
  arts in dementia care): the website's teams are plausible but noisier (long sentences,
  context-free list items); the AI-checked teams were better and name concrete gaps.
  Results are suggestions about published work, never about quality or availability.

### 5.6 Project builder (2026-11-06)
One page (`#/builder`, menu "Project builder" / "Prosjektbygger") that brings together
what a proposal needs. Built in milestones:

1. **Selection (done).** *Researchers*: the visitor's shortlist (also on the Shortlist
   page, which stays researchers-only), added with "+ Shortlist" on search results,
   profiles and in Find a team. *Funding calls*: added with "+ Project builder" on the
   Funding list and the call page; shown only here and only once Funding is unlocked,
   with funder/programme, deadline and status. Remove one entry or clear a list (a second
   press confirms). Calls that have **closed** (status, or every deadline passed) or
   **changed since saved** (status, deadlines, amounts, duration) are flagged; "Mark as
   checked" accepts a change. Both lists live in the browser (localStorage), without
   duplicates, survive reloads and stay in step across open tabs. For calls only the id,
   the date saved and those facts are stored, no call texts (`builder-core.ts`, tested in
   `tests/test_builder.py`).
2. **Prepare AI prompt (done).** Once Funding is unlocked: tick the researchers and calls
   to include (at least one of each), optionally give a research direction, application
   area and constraints, and choose the answer language. The site loads the calls' full
   details and assembles an English prompt (`prompt.ts` gathers, `prompt-core.ts`
   writes; tested in `tests/test_prompt.py`):
   - *Task and rules* for the external model: per call, assess the match on substance and
     do not force a concept when the team does not cover the call; otherwise a concept
     with title/acronym, summary, fit with the call, objectives and innovation,
     evidence-based roles, work packages, outcomes, missing expertise/partners,
     feasibility and eligibility, sources and assumptions. Facts are cited
     ([Call 1: …], [R2: publication 3]), the rest marked [Assumption]; eligibility is
     unverified unless the call states it; AI summaries are indications; nobody is said
     to have agreed to take part.
   - *Calls*: overview and deadlines, scope and objectives, expected outcomes, budget and
     duration, eligibility and consortium, evaluation and submission, the AI reading of
     the call (labelled), and the key requirements **not found** in the collected text.
   - *Researchers*: position and unit, profile links, AI summary (labelled), themes, the
     atlas match per call, and publications – those the matching found relevant to a
     selected call first, then recent ones.
   - *Preferences*, *sources and update dates*.
   Shown in an editable preview with "Copy prompt" and .md/.txt downloads. A field longer
   than 12 000 characters is shortened (listed, with the official link). Above 60 000
   characters the package is split: a compact prompt plus a "supporting information"
   file with everything in full. The site sends nothing; no direct transfer to AI tools.
3. **Project ideas (done).** No server: generated locally, saved and exported on the site.
   - *Selection file*: "Download selection for project ideas" (in Prepare AI prompt, same
     ticks and preferences) → `uis-atlas-selection-<date>.json`: researcher ids, each call
     id with its key facts at that moment, preferences, answer language, data dates.
   - *Generator*: `python pipeline/project_ideas.py <selection>.json` (`--dry-run`: what
     would be sent). One Claude request per call with the official call text, its key
     facts, the AI reading (labelled) and, per researcher, profile and summary (labelled)
     and numbered publications – relevant to that call first, abstract excerpts for the
     first five. Claude judges the fit (good / partial / poor) and writes a concept only
     when the team covers the call; a poor fit never gets one (reasons and missing
     expertise instead). Checked afterwards: evidence must cite a publication or profile
     shown for that researcher, quotes must occur in the call text, eligibility is
     "stated" only with a verified quote, roles and leads must be selected researchers,
     "R2" in prose becomes the name, text that repeats an abstract is flagged; the source
     list is built from known links, not by the model. Output
     `project-ideas-<date>.json`.
   - *Site*: "Import ideas file" → saved in the browser (kept when the selection changes),
     shown per idea with fit, call, date and researchers, labelled as an AI draft; the call
     is flagged when it has closed or changed since generation (facts from the selection
     file). Export per idea as Word (.docx, written in the browser by `docx.ts`, real
     heading styles) or Markdown; delete with a second press. Formats and rendering in
     `ideas-core.ts`; tests in `tests/test_ideas.py`.

### 5.4 Language
User interface in **Norwegian (bokmål) and English**, switchable. Researcher summaries in English for v1 (Norwegian optional later).

## 6. Quality requirements

- **Universal design:** UiS is a Norwegian public institution, so the site must meet WCAG 2.1 AA (required by Norwegian regulations on universal design). Keyboard navigation, visible focus, sufficient contrast, screen-reader labels, works without a mouse.
- **Responsive:** usable on phones.
- **Performance:** first search result within ~2 seconds on a normal laptop after initial load. Show a clear loading state while the embedding model downloads the first time (~100 MB, cached by the browser afterwards). Keyword search should work immediately while the model loads.
- **No tracking** beyond what UiS approves.

## 7. Visual design

Follow the UiS visual identity (logo, colours and typography from UiS’s official brand guidelines) if the project owner provides it. Ask before inventing a visual identity. The tone should be calm, credible and academic, with the search field as the clear focal point. Avoid generic “AI dashboard” styling (gradient washes, identical rounded cards everywhere, decorative motion).

## 8. Data protection and licensing

See `docs/DATA_POLICY.md`. In short: raw Scopus data never leaves the local machine or enters Git, the public site shows only derived summaries and bibliographic references, and researchers must be able to see, correct, or opt out of their profile.

## 9. Milestones

1. **Data:** run the collector, build profiles, review the unmatched-author list with the project owner, fix the department mapping.
2. **Summaries and embeddings:** generate and spot-check 20 summaries with the project owner.
3. **Search prototype:** minimal web page with hybrid search; evaluate with the query set.
4. **Full dashboard:** profile view, faculty overview, bilingual UI, accessibility pass.
5. **Launch preparation:** licence and GDPR confirmation, opt-out process, deployment, refresh routine (rerun pipeline each semester).

## 10. Open decisions (ask the project owner)

- Hosting: GitHub Pages, UiS servers, or another option? Public or private repository?
- Confirmation from the UiS Library on Scopus licence terms for the public site.
- Confirmation from the UiS data protection officer (personvernombud) on publishing researcher profiles.
- UiS brand guidelines (colours, fonts, logo usage).
- Include PhD candidates and postdocs, or permanent staff only? Include emeriti?
- Minimum activity threshold for inclusion (e.g. at least 2 publications in the period).
