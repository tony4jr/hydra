"""AdsPower Local API error hierarchy."""


class AdsPowerAPIError(RuntimeError):
    """Base for any AdsPower Local API failure."""


class AdsPowerQuotaExceeded(AdsPowerAPIError):
    """Profile quota reached — cannot create more."""
