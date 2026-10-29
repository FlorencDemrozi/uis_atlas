"""Central configuration for the UiS Researcher Atlas pipeline.

All paths, identifiers and tunable settings live here. Scripts import from
this module instead of hard-coding values.
"""
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# ---- Scope ---------------------------------------------------------------
AFID = "60014497"  # University of Stavanger in Scopus
FIRST_YEAR = int(os.environ.get("ATLAS_FIRST_YEAR", "2020"))
SCOPUS_QUERY = f"AF-ID({AFID}) AND PUBYEAR > {FIRST_YEAR - 1}"
# Once the full search is complete, every later run of collect_scopus.py searches
# only the last SCOPUS_REFRESH_YEARS calendar years again: new papers, papers
# indexed late and fresh citation counts for recent work (one weekly run costs a
# few hundred Search API requests).
SCOPUS_REFRESH_YEARS = 2
INSTITUTION_NAME = "University of Stavanger"

# Faculties and their departments (as of 2026-10-23, confirmed by the project owner).
# "phrases": lower-case English/Norwegian fragments that recognise a department in
# Scopus affiliation strings. All departments are checked in this order, so put
# more specific phrases first. "directory": unit ids in the UiS employee directory
# (www.uis.no/nb/sok/ansatte, facet "department:<id>"); a department without ids
# is assigned from Scopus affiliations only. "hints": faculty-level phrases.
FACULTIES = [
    {"name": "Faculty of Science and Technology", "directory": 1222,
     "hints": ["science and technology", "teknisk-naturvitenskapelig", "teknisk- naturvitenskapelig",
               "technology and natural sci", "technology and science", "sciences & technology"],
     "departments": [
         {"name": "Energy and Petroleum Engineering", "directory": [1268, 1250],
          "phrases": ["energy resources", "energiressurs", "petroleum"]},
         {"name": "Chemistry, Bioscience and Environmental Engineering", "directory": [1247],
          "phrases": ["chemistry", "bioscience", "environmental engineering", "kjemi",
                      "miljøteknikk", "miljøteknologi"]},
         {"name": "Electrical Engineering and Computer Science", "directory": [1256],
          "phrases": ["computer science", "electrical engineering", "elektro", "data- og"]},
         {"name": "Mathematics and Physics", "directory": [1259],
          "phrases": ["mathematics", "physics", "matematikk", "fysikk"]},
         {"name": "Mechanical and Structural Engineering and Materials Science", "directory": [1234],
          "phrases": ["mechanical", "structural engineering", "materials science", "maskin",
                      "konstruksjon"]},
         {"name": "Safety, Economics and Planning", "directory": [1223],
          "phrases": ["safety, economics", "safety economics", "industrial economics",
                      "risk management", "sikkerhet", "planlegging"]},
     ]},
    {"name": "Faculty of Arts and Education", "directory": 1224,
     "hints": ["arts and education", "education and arts", "utdanningsvitenskap og humaniora"],
     "departments": [
         {"name": "Department of Early Childhood Education", "directory": [1272],
          "phrases": ["early childhood", "barnehagelærer"]},
         {"name": "Department of Education and Sports Science", "directory": [1228],
          "phrases": ["education and sport", "sports science", "sport science", "grunnskolelærer",
                      "idrett og spesialpedagogikk"]},
         {"name": "Department of Cultural Studies and Languages", "directory": [1225],
          "phrases": ["cultural studies", "kultur- og språk"]},
     ]},
    {"name": "Faculty of Performing Arts", "directory": 1275,
     "hints": ["performing arts", "utøvende kunstfag"],
     "departments": [
         {"name": "Department of Jazz, Dance, Practical-Pedagogical Education and Music Production",
          "directory": [1276], "phrases": ["jazz", "dance", "music production", "musikkproduksjon"]},
         {"name": "Department of Classical Music", "directory": [1298],
          "phrases": ["classical music", "klassisk musikk"]},
     ]},
    {"name": "UiS School of Business and Law", "directory": 1229,
     "hints": ["business school", "school of business and law", "handelshøgskolen"],
     "departments": [
         {"name": "Department of Economics and Finance", "directory": [1249],
          "phrases": ["economics and finance", "samfunnsøkonomi og finans"]},
         {"name": "Department of Innovation, Management and Marketing", "directory": [1255],
          "phrases": ["innovation, management", "innovation, leadership", "department of innovation",
                      "management and marketing", "innovasjon, led"]},
         {"name": "Department of Accounting and Law", "directory": [1294],
          "phrases": ["accounting", "regnskap", "rettsvitenskap", "department of law"]},
     ]},
    {"name": "Faculty of Health Sciences", "directory": 1235,
     "hints": ["faculty of health", "health sciences", "helsevitenskap",
               "centre for resilience in healthcare", "center for resilience in healthcare"],
     "departments": [
         {"name": "Department of Public Health", "directory": [1243],
          "phrases": ["public health", "folkehelse"]},
         {"name": "Department of Quality and Health Technology", "directory": [1240],
          "phrases": ["quality and health technology", "health technology", "helseteknologi"]},
         {"name": "Department of Caring and Ethics", "directory": [1236],
          "phrases": ["caring and ethics", "care and ethics", "omsorg og etikk"]},
     ]},
    {"name": "Faculty of Social Sciences", "directory": 1241,
     "hints": ["faculty of social science", "samfunnsvitenskap"],
     "departments": [
         # Not a unit in the employee directory: assigned from Scopus affiliations only.
         {"name": "NHS – Department of Leadership and Service Innovation", "directory": [],
          "phrases": ["hotel management", "hotellhøgskole", "leadership and service innovation",
                      "service innovation"]},
         {"name": "Department of Media and Social Sciences", "directory": [1242],
          "phrases": ["media and social science", "medie- og samfunnsfag", "department of media"]},
         {"name": "Department of Social Studies", "directory": [1271],
          "phrases": ["social studies", "social work", "sosialfag"]},
         {"name": "Department of Psychology", "directory": [8977],
          "phrases": ["psychology", "psykologi"]},
     ]},
]

# Units deliberately left out (project owner, 2026-10-23): national centres and
# the museum. Their affiliation text never assigns a department or faculty.
EXCLUDED_UNIT_PHRASES = [
    "reading centre", "reading center", "reading education", "lesesenter", "leseopplæring",
    "learning environment", "læringsmiljø", "behavioural research in education",
    "behavioral research in education", "knowledge centre for education",
    "knowledge center for education", "kunnskapssenter for utdanning",
    "museum of archaeology", "archaeological museum", "arkeologisk museum",
]
# The same units in the employee directory: Norwegian Centre for Learning
# Environment, Norwegian Reading Centre, Knowledge Centre for Education, Museum
# of Archaeology. Staff listed only there are left out. Staff of a faculty's
# administration count as the faculty (department taken from Scopus if possible).
DIRECTORY_EXCLUDED_UNITS = [1269, 1226, 1227, 1260]


def not_stated(faculty: str) -> str:
    return f"{faculty} (department not stated)"


FACULTY_OF = {}  # department or "not stated" key -> faculty name
for _f in FACULTIES:
    FACULTY_OF[not_stated(_f["name"])] = _f["name"]
    for _d in _f["departments"]:
        FACULTY_OF[_d["name"]] = _f["name"]
NOT_STATED_KEYS = {not_stated(f["name"]) for f in FACULTIES}
DEPARTMENTS = [(d["name"], d["phrases"]) for f in FACULTIES for d in f["departments"]]
FACULTY_HINTS = [(f["name"], f["hints"]) for f in FACULTIES]
DIRECTORY_DEPARTMENTS = {uid: d["name"] for f in FACULTIES for d in f["departments"]
                         for uid in d["directory"]}
DIRECTORY_FACULTIES = {f["directory"]: f["name"] for f in FACULTIES}

# Former department names, checked BEFORE the current names above. Derived from
# authors whose affiliation changed over time; confirmed by the project owner
# 2026-10-22/23. "until": the name only means this for papers up to that year
# (later papers use normal matching). "became": None marks a split or unclear
# successor – the paper shows the faculty ("faculty") but not today's
# department, so it never decides a person's department on its own.
DEPARTMENT_HISTORY = [
    {"phrases": ["organelle research"],                       # CORE
     "became": "Chemistry, Bioscience and Environmental Engineering", "change": "moved"},
    {"phrases": ["mathematics and natural science", "mathematics and nat. sci",
                 "natural science and mathematics"],
     "became": None, "faculty": "Faculty of Science and Technology", "change": "split ~2018",
     "split_into": ["Chemistry, Bioscience and Environmental Engineering", "Mathematics and Physics"]},
    {"phrases": ["electrical and computer engineering", "elec./computer", "elec. and comp",
                 "eletrical and computer", "electr. and computer", "electrical and computer science",
                 "computer and electrical engineering", "electronic engineering and computer science",
                 "electrical eng. and comp"],
     "became": "Electrical Engineering and Computer Science", "change": "renamed"},
    {"phrases": ["industrial economics", "risk management and planning"],
     "became": "Safety, Economics and Planning", "change": "renamed ~2018"},
    {"phrases": ["department of health studies", "department of health sciences",
                 "institutt for helsefag"],
     "became": None, "faculty": "Faculty of Health Sciences", "change": "split"},
    {"phrases": ["department of business administration"],
     "became": None, "faculty": "UiS School of Business and Law", "change": "split"},
    {"phrases": ["department of social sciences"],
     "became": None, "faculty": "Faculty of Social Sciences", "change": "split"},
    {"phrases": ["teacher education", "lærerutdanning"],
     "became": None, "faculty": "Faculty of Arts and Education", "change": "split"},
]

# Periods for which the collector fetches at least one affiliation per author,
# so department history and current department are well grounded.
HISTORY_PERIODS = [(2000, 2009), (2010, 2017), (2018, 9999)]

# ---- Paths ---------------------------------------------------------------
DATA = ROOT / "data"
RAW = DATA / "raw" / "scopus"          # licensed, local only
INTERIM = DATA / "interim"             # licensed, local only
PUBLIC = DATA / "public"               # the only data the website may use
CONFIG_DIR = ROOT / "config"

RAW_DOCS = RAW / "docs.jsonl"
RAW_SEARCH_STATE = RAW / "search_state.json"
RAW_REFRESH = RAW / "refresh.jsonl"     # records of an unfinished refresh search
RAW_DETAILS = RAW / "details.jsonl"
RAW_ATLAS = RAW / "atlas_data.json"     # combined output of collect_scopus.py
RAW_DIRECTORY = DATA / "raw" / "uis_directory"  # UiS employee directory: personal data, local only
DIRECTORY = RAW_DIRECTORY / "employees.json"

PROFILES = INTERIM / "profiles.json"
MERGE_LOG = INTERIM / "merge_log.json"
REVIEW_DIR = INTERIM / "review"         # CSVs for the project owner (local only)
SUMMARIES = INTERIM / "summaries.json"
EMBEDDINGS_DIR = INTERIM / "embeddings"

LOGS = ROOT / "logs"                    # run_weekly.py logs (local only, not committed)

EXCLUSIONS = CONFIG_DIR / "exclusions.json"
OVERRIDES = CONFIG_DIR / "overrides.json"

# ---- Secrets (loaded from .env, never printed) ---------------------------
SCOPUS_API_KEY = os.environ.get("SCOPUS_API_KEY")
SCOPUS_INSTTOKEN = os.environ.get("SCOPUS_INSTTOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# ---- Summaries -----------------------------------------------------------
SUMMARY_MODEL = "claude-sonnet-5-5"
SUMMARY_MAX_PAPERS = 15        # most recent / most cited papers sent per researcher

# ---- Embeddings & ranking ------------------------------------------------
# Must match the browser model (Xenova/multilingual-e5-small) and prefixes.
EMBED_MODEL = "intfloat/multilingual-e5-small"
QUERY_PREFIX = "query: "
PASSAGE_PREFIX = "passage: "

RANKING = {
    "semantic_weight": 0.7,
    "keyword_weight": 0.3,
    "top_papers_per_researcher": 3,
    "recency_boost": 0.05,
}

# ---- Inclusion -----------------------------------------------------------
# A researcher is included with at least MIN_RECENT_PUBLICATIONS papers in the
# last RECENT_YEARS calendar years (REFERENCE_YEAR and the years before it).
# Papers dated after REFERENCE_YEAR (in press) also count as recent.
# People found in the UiS employee directory are confirmed current staff and
# are always included, whatever their publication record (project owner,
# 2026-10-28; MIN_RECENT_PUBLICATIONS = 0). Everyone else may have left UiS
# and needs the stricter UNCONFIRMED_* rule.
REFERENCE_YEAR = int(os.environ.get("ATLAS_REFERENCE_YEAR", date.today().year))
RECENT_YEARS = 3
MIN_RECENT_PUBLICATIONS = 0
UNCONFIRMED_RECENT_YEARS = 2
UNCONFIRMED_MIN_RECENT_PUBLICATIONS = 3

# ---- UiS employee directory ---------------------------------------------
DIRECTORY_URL = "https://www.uis.no/{lang}/{path}"   # path: "sok/ansatte" (nb), "search/employees" (en)
DIRECTORY_SLEEP = 1.0                               # seconds between requests: be polite

# ---- Recent work (project owner, 2026-10-26) -----------------------------
# Summaries, embeddings and funding matches use only papers from the last
# ACTIVE_YEARS calendar years (in-press papers count too). Researchers without
# such papers get no summary, vector or funding match.
ACTIVE_YEARS = 5
ACTIVE_FROM = REFERENCE_YEAR - ACTIVE_YEARS + 1


def is_active_paper(paper: dict) -> bool:
    year = str(paper.get("year") or "")
    return year.isdigit() and int(year) >= ACTIVE_FROM


# ---- Funding calls (Research Council of Norway) --------------------------
# Public call pages, collected politely by collect_rcn.py (robots.txt allows
# /utlysninger/; */Download is disallowed, so call PDFs are never fetched).
RAW_RCN = DATA / "raw" / "rcn"          # local cache of the call pages
# Call lists read on every run (project owner, 2026-10-27): RCN's current calls in
# Norwegian and English (the Norwegian list comes first, so its entry is kept when a
# call is on both), plus the completed list for history and change tracking.
RCN_LISTS = [
    ("https://www.forskningsradet.no/utlysninger/", "current"),
    ("https://www.forskningsradet.no/en/call-for-proposals/", "current"),
    ("https://www.forskningsradet.no/utlysninger/?timeframe=1", "completed"),
]
RCN_SLEEP = 1.0                                   # seconds between requests
USER_AGENT = "UiS-Researcher-Atlas/0.1 (+https://www.uis.no; research intelligence, weekly)"

# ---- EU funding (European Commission Funding & Tenders Portal) -----------
# Official public search API (the portal's own, key "SEDIA") for the topic list,
# and the portal's per-topic JSON for the full text. Every programme in the portal
# is imported (project owner, 2026-10-29): calls for proposals (type 1) and cascade
# calls run by EU-funded projects (type 2). Procurement tenders (type 8) are not
# research funding and are left out.
RAW_EU = DATA / "raw" / "eu"                      # local cache of topic records
EU_SEARCH_URL = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
EU_TOPIC_URL = "https://ec.europa.eu/info/funding-tenders/opportunities/data/topicDetails/{}.json"
EU_PORTAL_URL = ("https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/"
                 "topic-details/{}")
EU_TYPES = ["1", "2"]
EU_STATUS = {"31094501": "planned", "31094502": "open", "31094503": "closed"}
EU_CLOSED_MONTHS = 6          # closed topics kept for history: deadline within this many months
EU_DETAIL_MAX_AGE_DAYS = 28   # refetch an unchanged open topic's text at least this often
EU_SLEEP = 0.5                # seconds between requests

CALLS = INTERIM / "calls.json"                    # structured calls (build_calls.py)
CALLS_HISTORY = INTERIM / "calls_history.json"    # detected changes per call
CALL_PROFILES = INTERIM / "call_profiles.json"    # AI call profiles (profile_calls.py)
FUNDING_MATCHES = INTERIM / "funding_matches.json"
FUNDING_OVERRIDES = CONFIG_DIR / "funding_overrides.json"

# Researcher–call matching (match_funding.py). Initial values, not validated
# probabilities: the score ranks researchers for one call and is never a chance
# of being funded. Project experience is not scored yet (no project data).
FUNDING_MATCH = {
    "algorithm": "funding-match-1",
    "weights": {"scope": 0.5, "coverage": 0.3, "evidence": 0.2},
    "recency_half_life_years": 3,   # a paper from 3 years ago counts half
    "similarity": (0.80, 0.86),     # cosine similarity (multilingual-e5-small) mapped to
                                    # relevance: 0.80 or less -> 0, 0.86 or more -> 1.
                                    # Absolute, so a call nobody fits gets no High match.
    "keyword_weight": 0.2,          # share of paper relevance from distinctive title words
    "keyword_max_share": 0.01,      # a title word in more than 1% of UiS papers is not distinctive
    "relevant_paper": 0.5,          # relevance at which a paper counts as evidence
    "categories": {"high": 0.6, "medium": 0.35},
    "min_score": 0.25,
    "max_matches_per_call": 30,
    "specialists_per_aspect": 3,    # best researchers per aspect, listed even beyond the top matches
    "collaborators_per_match": 3,
    "max_aspects": 15,
}
