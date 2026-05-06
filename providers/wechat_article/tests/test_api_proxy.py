"""New unit tests for WECHAT_API_PROXY env support."""

from providers.wechat_article.internal.wechat_api import _api_base


def test_api_base_default(monkeypatch):
    monkeypatch.delenv("WECHAT_API_PROXY", raising=False)
    assert _api_base() == "https://api.weixin.qq.com/cgi-bin"


def test_api_base_with_proxy(monkeypatch):
    monkeypatch.setenv("WECHAT_API_PROXY", "https://wechat-bastion.example.com")
    assert _api_base() == "https://wechat-bastion.example.com/cgi-bin"


def test_api_base_strips_trailing_slash(monkeypatch):
    monkeypatch.setenv("WECHAT_API_PROXY", "https://wechat-bastion.example.com/")
    assert _api_base() == "https://wechat-bastion.example.com/cgi-bin"


def test_api_base_empty_string_env_falls_back(monkeypatch):
    """Empty string should be treated as unset."""
    monkeypatch.setenv("WECHAT_API_PROXY", "")
    assert _api_base() == "https://api.weixin.qq.com/cgi-bin"


def test_api_base_whitespace_only_env_falls_back(monkeypatch):
    monkeypatch.setenv("WECHAT_API_PROXY", "   ")
    assert _api_base() == "https://api.weixin.qq.com/cgi-bin"
