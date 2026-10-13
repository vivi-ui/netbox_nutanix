class VMwareError(Exception):
    """Base class for all VMware related errors."""


class VMwareAuthError(VMwareError):
    """Raised when authentication against the VMware API fails."""


class VMwareAPIError(VMwareError):
    """Raised when the VMware API returns an unexpected response."""
