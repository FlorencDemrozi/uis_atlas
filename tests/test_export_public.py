"""Slim public export: what the site can rebuild is left out of the files."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
from export_public import default_category  # noqa: E402


def test_default_category_matches_the_site():
    # web/src/data.ts: p.category ?? (p.type ? category_of[p.type] ?? "other" : "article")
    assert default_category({"type": "Conference Paper"}) == "conference"
    assert default_category({"type": "Article"}) == "article"
    assert default_category({"type": "Something new"}) == "other"
    assert default_category({}) == "article"   # NVA outputs have no type in papers.json
