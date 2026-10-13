from django.test import SimpleTestCase

from pysnmp.hlapi.asyncio import CommunityData, SnmpEngine, UsmUserData

from netbox_snmp.choices import (
    SnmpAuthProtocolChoices,
    SnmpPrivProtocolChoices,
    SnmpSecurityLevelChoices,
)
from netbox_snmp.exceptions import SnmpAuthError
from netbox_snmp.snmp.client import SnmpClient


class ClientAuthTestCase(SimpleTestCase):
    def test_v2c(self):
        client = SnmpClient('10.0.0.1', community='public')
        auth = client._auth_data()
        self.assertIsInstance(auth, CommunityData)

    def test_v2c_requires_community(self):
        client = SnmpClient('10.0.0.1')
        with self.assertRaises(SnmpAuthError):
            client._auth_data()

    def test_v3_no_auth_no_priv(self):
        client = SnmpClient(
            '10.0.0.1',
            version='3',
            security_username='user',
            security_level=SnmpSecurityLevelChoices.NO_AUTH_NO_PRIV,
        )
        self.assertIsInstance(client._auth_data(), UsmUserData)

    def test_v3_auth_no_priv(self):
        client = SnmpClient(
            '10.0.0.1',
            version='3',
            security_username='user',
            security_level=SnmpSecurityLevelChoices.AUTH_NO_PRIV,
            auth_protocol=SnmpAuthProtocolChoices.SHA256,
            auth_key='authkey',
        )
        self.assertIsInstance(client._auth_data(), UsmUserData)

    def test_v3_auth_priv(self):
        client = SnmpClient(
            '10.0.0.1',
            version='3',
            security_username='user',
            security_level=SnmpSecurityLevelChoices.AUTH_PRIV,
            auth_protocol=SnmpAuthProtocolChoices.SHA,
            auth_key='authkey',
            priv_protocol=SnmpPrivProtocolChoices.AES128,
            priv_key='privkey',
        )
        self.assertIsInstance(client._auth_data(), UsmUserData)

    def test_v3_requires_username(self):
        client = SnmpClient('10.0.0.1', version='3')
        with self.assertRaises(SnmpAuthError):
            client._auth_data()

    def test_v3_auth_requires_key(self):
        client = SnmpClient(
            '10.0.0.1',
            version='3',
            security_username='user',
            security_level=SnmpSecurityLevelChoices.AUTH_PRIV,
        )
        with self.assertRaises(SnmpAuthError):
            client._auth_data()


class ClientEngineTestCase(SimpleTestCase):
    def test_engine_is_created_per_run(self):
        client = SnmpClient('10.0.0.1', community='public')
        self.assertFalse(hasattr(client, '_engine'))

        seen = []

        async def probe(engine, tag):
            seen.append(isinstance(engine, SnmpEngine))
            return tag

        self.assertEqual(client._run(probe, 'a'), 'a')
        self.assertEqual(client._run(probe, 'b'), 'b')
        self.assertEqual(seen, [True, True])
