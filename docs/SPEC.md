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
- **Inclusion:** everyone found in the directory who has a Scopus profile, whatever their publication record (project owner, 2026-10-28); others (who may have left UiS) with ≥3 publications in the last 2 years (`config.py`). Staff without a Scopus profile will come from a staff list (Excel, with start and contract dates) later.
- **Period:** publications from 2020 onward (configurable via `ATLAS_FIRST_YEAR`).
- **Source:** Scopus (Elsevier), UiS affiliation ID `60014497`, via the Scopus API.
- Faculties and departments are configuration (`pipeline/config.py`, `web/src/org.ts`), not code.
- Known limitation: Scopus covers humanities, law and especially performing arts poorly, so those units look thinner than they are.

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
| 1b. Directory | `collect_directory.py` | UiS employee directory → `data/raw/uis_directory/` | Current staff, unit, position, profile link (nb + en). Any network; polite (~100 requests). |
| 2. Build profiles | `build_profiles.py` | raw → `data/interim/profiles.json` | One record per researcher: department, papers, keywords, co-authors, metrics. Handles name variants and duplicate Scopus author IDs. |
| 3. Summarize | `summarize.py` | profiles → `data/interim/summaries.json` | Uses the Claude API **offline** to write a 2–3 sentence overview and 3–6 topic tags per researcher. Cached and only regenerated when a profile changes. |
| 4. Embed | `embed.py` | profiles + summaries → `data/interim/embeddings.npy` | Semantic vectors for each researcher and for each paper (see §4). |
| 5. Export | `export_public.py` | interim → `data/public/` | Writes **only licence-safe fields** (see `DATA_POLICY.md`). This is the only data the website sees. |

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
