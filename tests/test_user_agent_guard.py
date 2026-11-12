from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FOLDERS = ("notebooks", "scripts")
SKIP_PARTS = {"__pycache__", ".ipynb_checkpoints"}


def _files():
    for folder in FOLDERS:
        for path in (ROOT / folder).rglob("*"):
            if path.is_file() and not SKIP_PARTS & set(path.parts):
                yield path


def test_no_browser_user_agent_under_notebooks_or_scripts():
    offenders = []
    for path in _files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "Mozilla/5.0" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"browser User-Agent string found in: {sorted(offenders)}"
