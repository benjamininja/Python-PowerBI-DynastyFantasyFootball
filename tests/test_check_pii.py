import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location("check_pii", REPO / "scripts" / "check_pii.py")
check_pii = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_pii)


def _contact_address() -> str:
    text = (REPO / "docs" / "DATA-USE.md").read_text(encoding="utf-8")
    found = check_pii.EMAIL_RE.findall(text)
    assert len(found) == 1
    return found[0]


def test_published_contact_address_is_allowed():
    addr = _contact_address()
    assert check_pii._allowed(addr)
    assert check_pii._scan_text("docs/DATA-USE.md", f"Write to {addr}.".encode()) == []


def test_other_address_on_same_domain_is_flagged():
    addr = _contact_address()
    other = "someone.else@" + addr.split("@", 1)[1]
    assert other != addr
    assert not check_pii._allowed(other)
    assert check_pii._scan_text("x.md", other.encode())
