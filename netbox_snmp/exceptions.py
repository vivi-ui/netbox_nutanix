class SnmpError(Exception):
    """Base class for all SNMP related errors."""


class SnmpAuthError(SnmpError):
    """Raised when authentication against a device fails."""


class SnmpTimeoutError(SnmpError):
    """Raised when a device does not respond to SNMP requests."""


class SyncCancelled(SnmpError):
    """Raised internally when a running sync has been asked to stop."""

