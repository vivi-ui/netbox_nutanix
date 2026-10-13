"""
Miscellaneous helpers for the SNMP plugin.
"""

import ipaddress
import re

# Addresses may be separated by newlines, commas, semicolons or whitespace.
_ADDRESS_SEPARATOR = re.compile(r'[\s,;]+')


def parse_target_addresses(text):
    """Split free-form text into normalized target addresses.

    Each token may be a single IPv4/IPv6 address or a network in CIDR notation.
    Returns a ``(valid, invalid)`` tuple where ``valid`` is an ordered,
    de-duplicated list of normalized address strings and ``invalid`` holds the
    tokens that could not be parsed.
    """
    valid = []
    invalid = []
    seen = set()

    for token in _ADDRESS_SEPARATOR.split(text or ''):
        token = token.strip()
        if not token:
            continue
        try:
            if '/' in token:
                value = str(ipaddress.ip_network(token, strict=False))
            else:
                value = str(ipaddress.ip_address(token))
        except ValueError:
            invalid.append(token)
            continue
        if value not in seen:
            seen.add(value)
            valid.append(value)

    return valid, invalid
