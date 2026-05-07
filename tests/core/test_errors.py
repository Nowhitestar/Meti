from core.errors import (
    ManifestError,
    MetiError,
    MissingCredentialError,
    PlatformRuleViolation,
    ProviderExecutionError,
    ProviderNotFoundError,
)


def test_hierarchy():
    assert issubclass(ManifestError, MetiError)
    assert issubclass(ProviderNotFoundError, MetiError)
    assert issubclass(MissingCredentialError, MetiError)
    assert issubclass(PlatformRuleViolation, MetiError)
    assert issubclass(ProviderExecutionError, MetiError)


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
