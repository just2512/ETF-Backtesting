"""Provider-side failures that must not be retried as transient transport errors."""


class ProviderQuotaExceeded(RuntimeError):
    """The provider has exhausted a request quota; wait for its reset window."""
