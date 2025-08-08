"""
Custom exceptions for the API Gateway.
"""


class TenantNotFoundError(Exception):
    """Raised when a tenant is not found for a given host."""

    pass


class TenantInactiveError(Exception):
    """Raised when a tenant is found but is inactive."""

    pass
