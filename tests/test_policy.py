"""Guards for docs/DATA_POLICY.md. Extend as the pipeline is implemented."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "data" / "public"


def test_no_abstract_field_in_public_data():
    for f in PUBLIC.glob("*.json"):
        text = f.read_text(encoding="utf-8")
        assert '"abstract"' not in text, f"{f.name} contains abstracts"
        assert '"affiliation_strings"' not in text, f"{f.name} contains raw affiliations"


def test_no_secrets_or_licensed_data_tracked_by_git():
    try:
        tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                                 text=True, check=True).stdout.splitlines()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return  # not a git repo yet
    for path in tracked:
        assert path != ".env", ".env is tracked by git"
        if path.startswith(("data/raw/", "data/interim/")):
            assert path.endswith(".gitkeep"), f"Licensed data tracked by git: {path}"


def test_embedding_model_matches_browser():
    """The browser must use the same model as the pipeline (SPEC §4.1)."""
    import sys
    sys.path.insert(0, str(ROOT / "pipeline"))
    import config
    web_cfg = ROOT / "web" / "src" / "search-config.json"
    if not web_cfg.exists():
        return  # web not scaffolded yet
    cfg = json.loads(web_cfg.read_text())
    assert cfg["model"].split("/")[-1] == config.EMBED_MODEL.split("/")[-1]
    assert cfg["queryPrefix"] == config.QUERY_PREFIX
