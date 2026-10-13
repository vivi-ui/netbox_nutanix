"""
Helpers to translate raw SNMP values into the primitives used by the sync engine.

Values returned by :mod:`pysnmp` are normalized to plain Python types by
:func:`to_python`; the remaining helpers decode the specific encodings used by
the standard MIBs (MAC addresses, addresses embedded in OIDs, netmasks, ...).
"""

import ipaddress

from pysnmp.proto import rfc1902

from dcim.choices import InterfaceTypeChoices

# Values larger than a single integer that pysnmp exposes as big integers
_INTEGER_TYPES = (
    rfc1902.Integer,
    rfc1902.Integer32,
    rfc1902.Counter32,
    rfc1902.Counter64,
    rfc1902.Gauge32,
    rfc1902.Unsigned32,
    rfc1902.TimeTicks,
)


def to_python(value):
    """Normalize an SNMP value object to a native Python value.

    * Integers, counters and timeticks become :class:`int`.
    * Bit/octet strings become :class:`bytes` (callers decode as needed).
    * Object identifiers and addresses become :class:`str`.
    """
    if value is None:
        return None
    if isinstance(value, _INTEGER_TYPES):
        return int(value)
    if isinstance(value, rfc1902.ObjectIdentifier):
        return value.prettyPrint()
    if isinstance(value, rfc1902.OctetString):
        return value.asOctets()
    return value.prettyPrint()


def decode_text(value):
    """Decode an octet string into text, discarding trailing NUL bytes."""
    if value is None:
        return ''
    if isinstance(value, str):
        return value.rstrip('\x00').strip()
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode('utf-8', errors='replace').rstrip('\x00').strip()
    return str(value).strip()


def bytes_to_mac(value):
    """Convert a 6-byte octet string into a colon-separated MAC address."""
    if not isinstance(value, (bytes, bytearray)):
        return None
    raw = bytes(value)
    if len(raw) != 6 or raw == b'\x00' * 6:
        return None
    return ':'.join(f'{byte:02x}' for byte in raw)


def bytes_to_ip(value):
    """Convert a 4- or 16-byte octet string into an IP address string."""
    if not isinstance(value, (bytes, bytearray)):
        return None
    raw = bytes(value)
    try:
        if len(raw) == 4:
            return str(ipaddress.IPv4Address(raw))
        if len(raw) == 16:
            address = ipaddress.IPv6Address(raw)
            return str(address)
    except (ipaddress.AddressValueError, ValueError):
        return None
    return None


def octets_to_ip(value):
    """Convert an OID sub-identifier sequence (ints) into an IP address string."""
    parts = [str(int(part)) for part in value]
    if len(parts) == 4:
        candidate = '.'.join(parts)
        try:
            return str(ipaddress.IPv4Address(candidate))
        except ipaddress.AddressValueError:
            return None
    if len(parts) == 16:
        try:
            raw = bytes(int(part) & 0xFF for part in value)
            return str(ipaddress.IPv6Address(raw))
        except (ValueError, ipaddress.AddressValueError):
            return None
    return None


def mask_to_prefix(value):
    """Convert a 4-byte IPv4 netmask octet string into a prefix length."""
    if not isinstance(value, (bytes, bytearray)):
        return None
    raw = bytes(value)
    if len(raw) != 4:
        return None
    binary = ''.join(f'{byte:08b}' for byte in raw)
    if '01' in binary:
        return None
    return binary.count('1')


def speed_kbps(high_speed, speed):
    """Return the interface speed in Kbps.

    ``ifHighSpeed`` is expressed in units of 1,000,000 bps (i.e. Mbps) while
    ``ifSpeed`` is expressed in bps. ``ifHighSpeed`` is preferred when present.
    """
    if high_speed:
        try:
            return int(high_speed) * 1000
        except (TypeError, ValueError):
            pass
    if speed:
        try:
            return int(speed) // 1000
        except (TypeError, ValueError):
            pass
    return None


def speed_bps(high_speed, speed):
    """Return the interface speed in bits per second (0 when unknown)."""
    kbps = speed_kbps(high_speed, speed)
    return (kbps or 0) * 1000


def map_interface_type(if_type, speed_bps_value=0):
    """Map an IANA ``ifType`` value onto a NetBox interface type."""
    if_type = int(if_type or 0)
    speed = int(speed_bps_value or 0)

    if if_type == 6:  # ethernetCsmacd
        if speed >= 400_000_000_000:
            return InterfaceTypeChoices.TYPE_400GE_QSFP_DD
        if speed >= 100_000_000_000:
            return InterfaceTypeChoices.TYPE_100GE_QSFP28
        if speed >= 40_000_000_000:
            return InterfaceTypeChoices.TYPE_40GE_QSFP_PLUS
        if speed >= 25_000_000_000:
            return InterfaceTypeChoices.TYPE_25GE_SFP28
        if speed >= 10_000_000_000:
            return InterfaceTypeChoices.TYPE_10GE_SFP_PLUS
        if speed >= 2_500_000_000:
            return InterfaceTypeChoices.TYPE_2GE_FIXED
        if speed >= 1_000_000_000:
            return InterfaceTypeChoices.TYPE_1GE_FIXED
        if speed >= 100_000_000:
            return InterfaceTypeChoices.TYPE_100ME_FIXED
        return InterfaceTypeChoices.TYPE_OTHER
    if if_type in (24, 53, 131, 135):  # loopback / virtual / tunnel / l2vlan
        return InterfaceTypeChoices.TYPE_VIRTUAL
    if if_type == 161:  # ieee8023adLag
        return InterfaceTypeChoices.TYPE_LAG
    return InterfaceTypeChoices.TYPE_OTHER


def port_list_to_ports(value):
    """
    Decode a BRIDGE/Q-BRIDGE ``PortList`` bitmap into 1-based port numbers.

    ``PortList`` encodes membership as one bit per bridge port, with the first
    bit of the first octet representing port 1 (RFC 2674 / RFC 4188).
    """
    if not isinstance(value, (bytes, bytearray)) or not value:
        return set()
    ports = set()
    for byte_index, byte in enumerate(bytes(value)):
        for bit in range(8):
            if byte & (0x80 >> bit):
                ports.add(byte_index * 8 + bit + 1)
    return ports


def mac_from_suffix(values):
    """Build a colon-separated MAC address from six OID sub-identifiers."""
    try:
        parts = [int(part) for part in values]
    except (TypeError, ValueError):
        return None
    if len(parts) != 6 or any(part < 0 or part > 255 for part in parts):
        return None
    return ':'.join(f'{part:02x}' for part in parts)
