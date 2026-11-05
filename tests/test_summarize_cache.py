"""Summary cache keys and link filtering for scraped call pages."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
from callfields import doc_links  # noqa: E402
from summarize import stable_hash  # noqa: E402

R = {"name": "Kari Nordmann"}
A = {"title": "Older paper", "year": "2023", "citations": 50, "category": "article"}
B = {"title": "Newer paper", "year": "2025", "citations": 1, "category": "article"}
C = {"title": "Another 2025 paper", "year": "2025", "citations": 9, "category": "article"}


def test_stable_hash_ignores_citation_order():
    # The same papers in a different order (citations changed) keep the cache key.
    assert stable_hash(R, [B, C, A]) == stable_hash(R, [C, B, A])


def test_stable_hash_changes_with_content():
    assert stable_hash(R, [B, C]) != stable_hash(R, [B, C, A])
    assert stable_hash(R, [B, C]) != stable_hash(R, [B, dict(C, title="Renamed")])


def test_doc_links_keep_web_links_only():
    secs = [{"path": ["Documents"], "links": [
        {"text": "Template", "url": "https://www.forskningsradet.no/mal.docx"},
        {"text": "Mail us", "url": "mailto:post@rcn.no"},
        {"text": "Evil", "url": "javascript:alert(1)"},
        {"text": "Evil 2", "url": "JavaScript:alert(1)"},
        {"text": "Data", "url": "data:text/html,hi"},
    ]}]
    assert [d["url"] for d in doc_links(secs)] == ["https://www.forskningsradet.no/mal.docx"]


# ---- which papers are selected, and when a cached summary is kept
import config  # noqa: E402
import summarize  # noqa: E402

PAPERS = {
    "e1": {"title": "One", "year": str(config.REFERENCE_YEAR), "citations": 1, "category": "article"},
    "e2": {"title": "Two", "year": str(config.REFERENCE_YEAR), "citations": 9, "category": "article"},
    "e3": {"title": "Three", "year": str(config.REFERENCE_YEAR - 1), "citations": 0, "category": "article"},
    "e4": {"title": "Four", "year": str(config.ACTIVE_FROM), "citations": 0, "category": "article"},
}
P = {"scopus_id": "1", "name": "Kari Nordmann", "paper_ids": ["e1", "e2", "e3", "e4"]}


def entry(ids, **kw):
    return dict({"summary": "Kari Nordmann studies things.", "tags": ["a", "b", "c"], "paper_ids": ids,
                 "prompt_version": summarize.PROMPT_VERSION, "name": P["name"],
                 "model": config.SUMMARY_MODEL, "source_hash": "x"}, **kw)


def test_selection_ignores_citations(monkeypatch):
    monkeypatch.setattr(config, "SUMMARY_MAX_PAPERS", 1)
    assert summarize.select_ids(P, PAPERS) == ["e1"]                       # tie: paper id
    more = dict(PAPERS, e1=dict(PAPERS["e1"], citations=0), e2=dict(PAPERS["e2"], citations=99))
    assert summarize.select_ids(P, more) == ["e1"]                         # a citation refresh changes nothing
    assert summarize.select_ids(P, PAPERS, by_citations=True) == ["e2"]    # the earlier rule


def test_summary_kept_when_papers_only_age_out():
    ids = summarize.select_ids(P, PAPERS)
    assert ids == ["e1", "e2", "e3", "e4"]
    assert summarize.cached_basis(entry(ids), P, PAPERS) == ids
    aged = dict(PAPERS, e4=dict(PAPERS["e4"], year=str(config.ACTIVE_FROM - 1)))   # 1 January
    assert summarize.cached_basis(entry(ids), P, aged) == ids


def test_new_summary_when_a_paper_enters_or_most_aged_out():
    assert summarize.cached_basis(entry(["e1", "e2", "e3"]), P, PAPERS) is None    # e4 is new
    old = entry(["e1", "e2", "e3", "e4", "gone1", "gone2", "gone3", "gone4", "gone5"])
    assert summarize.cached_basis(old, P, PAPERS) is None                          # fewer than half left


def test_new_summary_when_model_prompt_or_name_changes():
    ids = summarize.select_ids(P, PAPERS)
    assert summarize.cached_basis(entry(ids, model="another-model"), P, PAPERS) is None
    assert summarize.cached_basis(entry(ids, prompt_version=summarize.PROMPT_VERSION + 1), P, PAPERS) is None
    assert summarize.cached_basis(entry(ids, name="Kari N. Nordmann"), P, PAPERS) is None


def test_entries_without_paper_ids_fall_back_to_the_hash(monkeypatch):
    ids = summarize.select_ids(P, PAPERS)
    legacy = {"summary": "s", "tags": [], "model": config.SUMMARY_MODEL}
    h = summarize.stable_hash(P, [PAPERS[e] for e in ids])
    assert summarize.cached_basis(dict(legacy, source_hash=h), P, PAPERS) == ids
    assert summarize.cached_basis(dict(legacy, source_hash="other"), P, PAPERS) is None
    # Written under the citation tie-break: recognised, and kept as long as nothing new entered.
    monkeypatch.setattr(config, "SUMMARY_MAX_PAPERS", 1)
    old = summarize.select_ids(P, PAPERS, by_citations=True)
    h_old = summarize.stable_hash(P, [PAPERS[e] for e in old])
    assert summarize.cached_basis(dict(legacy, source_hash=h_old), P, PAPERS) is None   # e1 is new to it


def test_only_valid_tags_are_stored():
    assert summarize.clean_tags([" lidar ", "", "x" * 51, 3, "remote sensing"]) == ["lidar", "remote sensing"]
