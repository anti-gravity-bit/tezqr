from __future__ import annotations


class TezQRError(Exception):
    """Base exception for business errors."""


class DomainValidationError(TezQRError):
    """Raised when a value object or entity is invalid."""


class AuthorizationError(TezQRError):
    """Raised when an actor is not allowed to perform an action."""


class MerchantNotFoundError(TezQRError):
    """Raised when a merchant is required but missing."""


class MerchantSetupRequiredError(TezQRError):
    """Raised when a merchant has not completed UPI setup."""


class FreeQuotaExceededError(TezQRError):
    """Raised when the free generation quota has been exhausted."""
