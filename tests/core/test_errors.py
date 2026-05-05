import pytest
from core.errors import (
    MMPError,
    ManifestError,
    ProviderNotFoundError,
    MissingCredentialError,
    PlatformRuleViolation,
    ProviderExecutionError,
)


def test_hierarchy():
    assert issubclass(ManifestError, MMPError)
    assert issubclass(ProviderNotFoundError, MMPError)
    assert issubclass(MissingCredentialError, MMPError)
    assert issubclass(PlatformRuleViolation, MMPError)
    assert issubclass(ProviderExecutionError, MMPError)


def test_provider_execution_error_carries_metadata():
    upstream = ValueError("boom")
    err = ProviderExecutionError(
        target="wechat-article",
        step="upload_thumb",
        upstream=upstream,
        retryable=True,
    )
    assert err.target == "wechat-article"
    assert err.step == "upload_thumb"
    assert err.upstream is upstream
    assert err.retryable is True


def test_missing_credential_error_carries_provider_and_keys():
    err = MissingCredentialError(provider="wechat-article", keys=["WECHAT_APP_ID"])
    assert err.provider == "wechat-article"
    assert err.keys == ["WECHAT_APP_ID"]
