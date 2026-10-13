class NutanixError(Exception):
    """Base class for all Nutanix related errors."""


class NutanixAuthError(NutanixError):
    """Raised when authentication against the Nutanix API fails."""


class NutanixAPIError(NutanixError):
    """Raised when the Nutanix API returns an unexpected response."""
