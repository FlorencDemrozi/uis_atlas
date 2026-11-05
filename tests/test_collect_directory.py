"""collect_directory.py: a short listing writes nothing; e-mail choice. No network."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
import collect_directory as cd  # noqa: E402
import config  # noqa: E402


@pytest.fixture
def directory_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_RUN_LOCKED", "1")
    monkeypatch.setattr(config, "RAW_DIRECTORY", tmp_path)
    monkeypatch.setattr(config, "DIRECTORY", tmp_path / "employees.json")
    monkeypatch.setattr(config, "DIRECTORY_EMAILS", tmp_path / "emails.json")
    monkeypatch.setattr(cd, "fetch", lambda s, lang, unit=None, page=0: "")
    monkeypatch.setattr(cd, "facets", lambda page: {"1": ("Unit", 100)})
    (tmp_path / "employees.json").write_text('{"old": true}', encoding="utf-8")
    (tmp_path / "emails.json").write_text('{"https://www.uis.no/nb/profile/x": "x@uis.no"}', encoding="utf-8")
    return tmp_path


def people(n):
    return [{"url": f"https://www.uis.no/nb/profile/p{i}", "name": f"P {i}", "position": None} for i in range(n)]


@pytest.mark.parametrize("n", [0, 50])
def test_short_listing_stops_without_writing(directory_env, monkeypatch, n):
    monkeypatch.setattr(cd, "members", lambda s, lang, unit, count: people(n))
    monkeypatch.setattr(cd, "add_emails", lambda s, p: pytest.fail("e-mail cache must not be touched"))
    with pytest.raises(SystemExit) as exc:
        cd.main()
    assert exc.value.code == 1
    assert json.loads((directory_env / "employees.json").read_text(encoding="utf-8")) == {"old": True}
    assert "x@uis.no" in (directory_env / "emails.json").read_text(encoding="utf-8")


def test_complete_listing_is_written(directory_env, monkeypatch):
    monkeypatch.setattr(cd, "members", lambda s, lang, unit, count: people(95))
    monkeypatch.setattr(cd, "add_emails", lambda s, p: None)
    cd.main()
    out = json.loads((directory_env / "employees.json").read_text(encoding="utf-8"))
    assert len(out["employees"]) == 95
    assert cd.listing_complete(90, 100) and not cd.listing_complete(89, 100) and not cd.listing_complete(0, 0)


def test_email_prefers_the_persons_own_address():
    page = ('<a href="mailto:post@uis.no">post</a> <a href="mailto:iks-kontor@uis.no">unit</a> '
            '<a href="mailto:oyvind.saether@uis.no">me</a>')
    assert cd.email_of(page, "Øyvind Sæther") == "oyvind.saether@uis.no"
    assert cd.email_of(page) == "iks-kontor@uis.no"            # no name: first non-generic address
    assert cd.email_of(page, "Kari Nordmann") == "iks-kontor@uis.no"
    assert cd.email_of('<a href="mailto:post@uis.no">x</a>', "Kari") is None
