class BeckhoffAdsError(Exception):
    """Base exception for the integration."""

class BeckhoffAdsConnectionError(BeckhoffAdsError):
    """The PLC connection could not be established or was lost."""

class BeckhoffAdsReadError(BeckhoffAdsError):
    """A PLC read failed."""

class BeckhoffAdsWriteError(BeckhoffAdsError):
    """A PLC write failed."""

class BeckhoffAdsConfigurationError(BeckhoffAdsError):
    """The PLC configuration is invalid."""
