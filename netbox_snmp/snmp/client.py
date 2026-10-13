"""
A thin synchronous wrapper around the pysnmp asynchronous high-level API.

NetBox performs discovery from background workers, so the client exposes plain
synchronous methods while delegating the actual request handling to
:mod:`pysnmp.hlapi.asyncio` via :func:`asyncio.run`.
"""

import asyncio

from pysnmp.hlapi.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    UsmUserData,
    USM_AUTH_HMAC96_MD5,
    USM_AUTH_HMAC96_SHA,
    USM_AUTH_HMAC128_SHA224,
    USM_AUTH_HMAC192_SHA256,
    USM_AUTH_HMAC256_SHA384,
    USM_AUTH_HMAC384_SHA512,
    USM_PRIV_CBC56_DES,
    USM_PRIV_CBC168_3DES,
    USM_PRIV_CFB128_AES,
    USM_PRIV_CFB192_AES,
    USM_PRIV_CFB256_AES,
    get_cmd,
    walk_cmd,
)

from ..choices import (
    SnmpAuthProtocolChoices,
    SnmpPrivProtocolChoices,
    SnmpSecurityLevelChoices,
    SnmpVersionChoices,
)
from ..exceptions import SnmpAuthError, SnmpError, SnmpTimeoutError
from . import oids
from .parsers import to_python

AUTH_PROTOCOLS = {
    SnmpAuthProtocolChoices.MD5: USM_AUTH_HMAC96_MD5,
    SnmpAuthProtocolChoices.SHA: USM_AUTH_HMAC96_SHA,
    SnmpAuthProtocolChoices.SHA224: USM_AUTH_HMAC128_SHA224,
    SnmpAuthProtocolChoices.SHA256: USM_AUTH_HMAC192_SHA256,
    SnmpAuthProtocolChoices.SHA384: USM_AUTH_HMAC256_SHA384,
    SnmpAuthProtocolChoices.SHA512: USM_AUTH_HMAC384_SHA512,
}

PRIV_PROTOCOLS = {
    SnmpPrivProtocolChoices.DES: USM_PRIV_CBC56_DES,
    SnmpPrivProtocolChoices.TRIPLE_DES: USM_PRIV_CBC168_3DES,
    SnmpPrivProtocolChoices.AES128: USM_PRIV_CFB128_AES,
    SnmpPrivProtocolChoices.AES192: USM_PRIV_CFB192_AES,
    SnmpPrivProtocolChoices.AES256: USM_PRIV_CFB256_AES,
}


def index_suffix(base_oid, oid):
    """Return the list of integer sub-identifiers following ``base_oid``."""
    base = base_oid.rstrip('.')
    oid = str(oid).lstrip('.')
    if oid == base:
        return []
    if not oid.startswith(base + '.'):
        return []
    return [int(part) for part in oid[len(base) + 1:].split('.') if part]


class SnmpClient:
    """
    Synchronous SNMP client bound to a single device address.
    """

    def __init__(
        self,
        host,
        port=161,
        version=SnmpVersionChoices.V2C,
        community=None,
        security_username=None,
        security_level=SnmpSecurityLevelChoices.AUTH_PRIV,
        auth_protocol=SnmpAuthProtocolChoices.SHA,
        auth_key=None,
        priv_protocol=SnmpPrivProtocolChoices.AES128,
        priv_key=None,
        timeout=5,
        retries=2,
    ):
        self.host = host
        self.port = int(port or 161)
        self.version = version
        self.community = community
        self.security_username = security_username
        self.security_level = security_level
        self.auth_protocol = auth_protocol
        self.auth_key = auth_key
        self.priv_protocol = priv_protocol
        self.priv_key = priv_key
        self.timeout = float(timeout or 5)
        self.retries = int(retries or 0)

    #
    # Auth construction
    #

    def _auth_data(self):
        if self.version == '3':
            return self._usm_user()
        if not self.community:
            raise SnmpAuthError("An SNMPv2c community string is required")
        return CommunityData(self.community, mpModel=1)

    def _usm_user(self):
        if not self.security_username:
            raise SnmpAuthError("An SNMPv3 security username is required")

        if self.security_level == SnmpSecurityLevelChoices.NO_AUTH_NO_PRIV:
            return UsmUserData(self.security_username)

        auth_protocol = AUTH_PROTOCOLS.get(self.auth_protocol, USM_AUTH_HMAC96_SHA)
        if not self.auth_key:
            raise SnmpAuthError("An SNMPv3 authentication key is required")

        if self.security_level == SnmpSecurityLevelChoices.AUTH_NO_PRIV:
            return UsmUserData(
                self.security_username,
                self.auth_key,
                authProtocol=auth_protocol,
            )

        priv_protocol = PRIV_PROTOCOLS.get(self.priv_protocol, USM_PRIV_CFB128_AES)
        if not self.priv_key:
            raise SnmpAuthError("An SNMPv3 privacy key is required")
        return UsmUserData(
            self.security_username,
            self.auth_key,
            self.priv_key,
            authProtocol=auth_protocol,
            privProtocol=priv_protocol,
        )

    async def _transport(self):
        address = (self.host, self.port)
        timeout = self.timeout
        retries = self.retries
        try:
            return await UdpTransportTarget.create(address, timeout=timeout, retries=retries)
        except TypeError:
            # Older pysnmp releases construct the transport target synchronously.
            return UdpTransportTarget(address, timeout=timeout, retries=retries)

    #
    # Public API
    #

    def _run(self, coro, *args, **kwargs):
        """
        Run ``coro`` against a freshly created :class:`SnmpEngine`.

        A pysnmp engine binds its transport dispatcher to the event loop that is
        active when the engine is created, so it must be instantiated *inside*
        the loop that :func:`asyncio.run` spins up. Reusing one engine across
        successive ``asyncio.run`` calls leaves later requests waiting on a loop
        that is no longer running, which makes the background worker hang.
        """

        async def runner():
            engine = SnmpEngine()
            return await coro(engine, *args, **kwargs)

        return asyncio.run(runner())

    def get(self, oid_list):
        """Issue a single GET request and return ``{oid: value}``."""
        if not oid_list:
            return {}
        return self._run(self._get, oid_list)

    def walk(self, oid, max_rows=None):
        """Walk a subtree and return ``{oid: value}`` for every returned row."""
        return self._run(self._walk, oid, max_rows=max_rows)

    def test_connection(self):
        """Verify that the device answers a basic GET request."""
        result = self.get([oids.SYS_DESCR])
        if not result.get(oids.SYS_DESCR):
            raise SnmpTimeoutError(f"No response received from {self.host}")

    def get_system(self):
        """Return the SNMPv2-MIB ``system`` group as a dictionary."""
        result = self.get(list(oids.SYSTEM_OIDS.values()))
        return {name: result.get(oid) for name, oid in oids.SYSTEM_OIDS.items()}

    #
    # Internals
    #

    async def _get(self, engine, oid_list):
        auth_data = self._auth_data()
        transport = await self._transport()
        var_binds = [ObjectType(ObjectIdentity(oid)) for oid in oid_list]

        error_indication, error_status, error_index, result = await get_cmd(
            engine,
            auth_data,
            transport,
            ContextData(),
            *var_binds,
        )
        self._raise_for_error(error_indication, error_status, error_index)

        return {str(name): to_python(value) for name, value in result}

    async def _walk(self, engine, oid, max_rows=None):
        auth_data = self._auth_data()
        transport = await self._transport()

        results = {}
        rows = 0
        generator = walk_cmd(
            engine,
            auth_data,
            transport,
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
            lexicographicMode=False,
        )
        async for error_indication, error_status, error_index, var_binds in generator:
            self._raise_for_error(error_indication, error_status, error_index)
            for name, value in var_binds:
                results[str(name)] = to_python(value)
                rows += 1
            if max_rows is not None and rows >= max_rows:
                break
        return results

    @staticmethod
    def _raise_for_error(error_indication, error_status, error_index):
        if error_indication:
            message = str(error_indication)
            lowered = message.lower()
            if 'timeout' in lowered or 'no response' in lowered:
                raise SnmpTimeoutError(message)
            if 'authentication' in lowered or 'authorization' in lowered or 'unknown user' in lowered:
                raise SnmpAuthError(message)
            raise SnmpError(message)
        if error_status:
            raise SnmpError(f"{error_status.prettyPrint()} at {error_index}")
