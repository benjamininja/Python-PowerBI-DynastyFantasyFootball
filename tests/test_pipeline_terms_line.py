import check_sources
import run_pipeline as rp


def _summary():
    return rp.summarize("INSEASON", "8", [], {}, "no data changes — commit skipped")


def test_count_shown(monkeypatch):
    monkeypatch.setattr(check_sources, "terms_due_count", lambda data: 4)
    assert rp.terms_line() == "📜 Terms checks due: 4"
    assert "📜 Terms checks due: 4" in _summary()


def test_zero_says_so(monkeypatch):
    monkeypatch.setattr(check_sources, "terms_due_count", lambda data: 0)
    assert rp.terms_line() == "📜 Terms checks due: 0"
    assert "📜 Terms checks due: 0" in _summary()


def test_load_error_is_unavailable_not_raised(monkeypatch):
    def boom():
        raise OSError("sources.yml missing")

    monkeypatch.setattr(check_sources, "load_yaml", boom)
    assert "unavailable" in rp.terms_line()
    assert "unavailable" in _summary()


def test_count_error_is_unavailable(monkeypatch):
    def boom(data):
        raise ValueError("bad block")

    monkeypatch.setattr(check_sources, "terms_due_count", boom)
    assert "unavailable" in _summary()


def test_line_uses_real_count(monkeypatch):
    want = check_sources.terms_due_count(check_sources.load_yaml())
    assert rp.terms_line() == f"📜 Terms checks due: {want}"
