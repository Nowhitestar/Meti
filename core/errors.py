"""Exception hierarchy for meti core."""

from __future__ import annotations


class MetiError(Exception):
    """Base class for all meti errors."""


class ManifestError(MetiError):
    """Manifest schema or validation failure."""


class ProviderNotFoundError(MetiError):
    """Requested provider not registered."""


class MissingCredentialError(MetiError):
    """Required credentials not available in vault or ENV."""

    def __init__(self, provider: str, keys: list[str]) -> None:
        self.provider = provider
        self.keys = keys
        super().__init__(f"missing credentials for {provider}: {keys}")


class PlatformRuleViolation(MetiError):
    """Manifest violates a provider's platform rules at error severity."""


class ProviderExecutionError(MetiError):
    """Provider.execute raised; carries enough metadata for resume."""

    def __init__(
        self,
        target: str,
        step: str,
        upstream: Exception | None = None,
        retryable: bool = False,
    ) -> None:
        self.target = target
        self.step = step
        self.upstream = upstream
        self.retryable = retryable
        msg = f"{target} failed at {step}: {upstream}"
        super().__init__(msg)
