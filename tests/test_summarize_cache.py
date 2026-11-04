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
