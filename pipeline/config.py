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
FACULTY_NAME = "Faculty of Science and Technology"

# Departments of the faculty, with English and Norwegian name fragments used to
# recognise them in Scopus affiliation strings. Order matters: more specific first.
# To add another faculty later, extend this structure rather than the scripts.
DEPARTMENTS = [
    ("Energy Resources", ["energy resources", "energiressurs"]),
    ("Energy and Petroleum Engineering", ["petroleum"]),
    ("Chemistry, Bioscience and Environmental Engineering",
     ["chemistry", "bioscience", "environmental engineering", "kjemi", "miljøteknikk"]),
    ("Computer Science and Electrical Engineering",
     ["computer science", "electrical engineering", "elektro", "data- og"]),
    ("Mathematics and Physics", ["mathematics", "physics", "matematikk", "fysikk"]),
    ("Mechanical and Structural Engineering and Materials Science",
     ["mechanical", "structural engineering", "materials science", "maskin", "konstruksjon"]),
    ("Safety, Economics and Planning",
     ["safety, economics", "safety economics", "industrial economics",
      "risk management", "sikkerhet", "planlegging"]),
]
FACULTY_HINTS = ["science and technology", "teknisk-naturvitenskapelig",
                 "technology and natural sci", "technology and science", "sciences & technology"]
NOT_STATED = f"{FACULTY_NAME} (department not stated)"

# Former department names, checked BEFORE the current names above. Derived from
# authors whose affiliation changed over time; confirmed by the project owner
# 2026-10-22. "until": the name only means this for papers up to that year
# (later papers use normal matching). "became": None marks a split – the paper
# shows the faculty but not today's department, so it never decides a person's
# department on its own.
DEPARTMENT_HISTORY = [
    {"phrases": ["organelle research"],                       # CORE
     "became": "Chemistry, Bioscience and Environmental Engineering", "change": "moved"},
    {"phrases": ["mathematics and natural science", "mathematics and nat. sci",
                 "natural science and mathematics"],
     "became": None, "change": "split ~2018",
     "split_into": ["Chemistry, Bioscience and Environmental Engineering", "Mathematics and Physics"]},
    {"phrases": ["petroleum engineering", "petroleum technology"], "until": 2017,
     "became": None, "change": "split ~2018",
     "split_into": ["Energy Resources", "Energy and Petroleum Engineering"]},
    {"phrases": ["electrical and computer engineering", "elec./computer", "elec. and comp",
                 "eletrical and computer", "electr. and computer", "electrical and computer science",
                 "computer and electrical engineering", "electronic engineering and computer science",
                 "electrical eng. and comp"],
     "became": "Computer Science and Electrical Engineering", "change": "renamed"},
    {"phrases": ["industrial economics", "risk management and planning"],
     "became": "Safety, Economics and Planning", "change": "renamed ~2018"},
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
RAW_DETAILS = RAW / "details.jsonl"
RAW_ATLAS = RAW / "atlas_data.json"     # combined output of collect_scopus.py

PROFILES = INTERIM / "profiles.json"
MERGE_LOG = INTERIM / "merge_log.json"
REVIEW_DIR = INTERIM / "review"         # CSVs for the project owner (local only)
SUMMARIES = INTERIM / "summaries.json"
EMBEDDINGS_DIR = INTERIM / "embeddings"

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
REFERENCE_YEAR = int(os.environ.get("ATLAS_REFERENCE_YEAR", date.today().year))
RECENT_YEARS = 2
MIN_RECENT_PUBLICATIONS = 3
