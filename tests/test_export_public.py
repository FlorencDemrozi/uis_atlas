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


def test_funding_files_are_only_rewritten_when_content_changes(tmp_path, monkeypatch):
    import json
    import export_funding as ef
    salt, password = b"0123456789abcdef", "correct horse"
    key = ef.derive_key(password, salt)
    plain = json.dumps({"meta": {"generated": "2026-11-01T01:00:00", "n": 1}, "calls": [1, 2]})
    path = tmp_path / "funding.enc.json"
    path.write_text(json.dumps(ef.encrypt(plain.encode(), key, salt)), encoding="utf-8")
    monkeypatch.setattr(ef, "OUT", path)

    assert ef.previous_key(password) == (salt, key)
    assert ef.previous_key("another password") is None          # new password: new salt, all rewritten
    # Same content a week later: only the export time differs -> kept.
    later = plain.replace("2026-11-01T01:00:00", "2026-11-08T01:00:00")
    assert ef.unchanged(path, later, key, salt)
    assert not ef.unchanged(path, plain.replace("[1, 2]", "[1, 2, 3]"), key, salt)
    assert not ef.unchanged(path, plain, key, b"fedcba9876543210")
    assert not ef.unchanged(tmp_path / "missing.enc.json", plain, key, salt)
