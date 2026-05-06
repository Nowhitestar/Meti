import pytest

from core.wizard.loader import list_stages, render


def test_list_stages():
    stages = list_stages()
    assert "source_extraction" in stages
    assert "target_selection" in stages
    assert "manifest_assembly" in stages
    assert "credential_setup" in stages


def test_render_basic_substitution(tmp_path):
    # write a tiny test prompt to a temp dir and render it
    test_prompt = tmp_path / "demo.md"
    test_prompt.write_text("Hello, {{name}}!\n", encoding="utf-8")
    out = render(test_prompt, name="World")
    assert out.strip() == "Hello, World!"


def test_render_missing_var_raises(tmp_path):
    test_prompt = tmp_path / "x.md"
    test_prompt.write_text("Hello {{missing}}", encoding="utf-8")
    with pytest.raises(KeyError):
        render(test_prompt)


def test_render_real_stage_returns_text():
    text = render("source_extraction")
    assert len(text) > 0
    assert isinstance(text, str)
