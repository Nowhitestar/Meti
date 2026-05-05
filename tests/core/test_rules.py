from types import SimpleNamespace

from core.rules import PlatformRules, Severity, Violation


def _stub_manifest(**overrides):
    base = dict(title="hello", body="body", images=[], tags=[])
    base.update(overrides)
    return SimpleNamespace(**base)


def test_violation_default_severity_error():
    v = Violation(code="X", message="x")
    assert v.severity == Severity.error


def test_lint_title_max():
    rules = PlatformRules(title_max=10)
    m = _stub_manifest(title="this is too long for the limit")
    vs = rules.lint(m, target_name="xhs")
    assert any(v.code == "TITLE_TOO_LONG" for v in vs)


def test_lint_image_count_min():
    rules = PlatformRules(image_count_min=3)
    m = _stub_manifest(images=["a.png"])
    vs = rules.lint(m, target_name="xhs")
    assert any(v.code == "IMAGE_COUNT_BELOW_MIN" for v in vs)


def test_lint_image_count_max():
    rules = PlatformRules(image_count_max=2)
    m = _stub_manifest(images=["a.png", "b.png", "c.png"])
    vs = rules.lint(m, target_name="xhs")
    assert any(v.code == "IMAGE_COUNT_ABOVE_MAX" for v in vs)


def test_lint_clean_passes():
    rules = PlatformRules(title_max=20, image_count_min=1, image_count_max=9)
    m = _stub_manifest(title="short", images=["a.png"])
    assert rules.lint(m, target_name="xhs") == []


def test_extra_lints_invoked():
    def custom(m, target_name):
        return [Violation(code="CUSTOM", message="x", severity=Severity.warning)]

    rules = PlatformRules(extra_lints=[custom])
    m = _stub_manifest()
    vs = rules.lint(m, target_name="any")
    assert any(v.code == "CUSTOM" for v in vs)
