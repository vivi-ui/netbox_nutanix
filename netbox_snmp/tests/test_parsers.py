from django.test import SimpleTestCase
from pysnmp.hlapi.asyncio import SnmpEngine
from pysnmp.proto import rfc1902
from pysnmp.smi.rfc1902 import ObjectIdentity
from pysnmp.smi.view import MibViewController

from dcim.choices import InterfaceTypeChoices

from netbox_snmp.snmp import parsers
from netbox_snmp.snmp.client import index_suffix


class ToPythonTestCase(SimpleTestCase):
    def test_integer(self):
        self.assertEqual(parsers.to_python(rfc1902.Integer(42)), 42)

    def test_octet_string(self):
        self.assertEqual(parsers.to_python(rfc1902.OctetString(b'abc')), b'abc')

    def test_object_identifier_is_numeric(self):
        self.assertEqual(
            parsers.to_python(rfc1902.ObjectIdentifier('1.3.6.1.4.1.9.1.2494')),
            '1.3.6.1.4.1.9.1.2494',
        )

    def test_object_identity_is_numeric(self):
        # pysnmp returns GET/WALK values as a *resolved* ObjectIdentity, which
        # would otherwise prettyPrint to a symbolic name such as
        # ``SNMPv2-SMI::enterprises.9.1.2494``.
        engine = SnmpEngine()
        mib_view = MibViewController(engine.get_mib_builder())
        identity = ObjectIdentity('1.3.6.1.4.1.9.1.2494')
        identity.resolve_with_mib(mib_view)
        self.assertEqual(parsers.to_python(identity), '1.3.6.1.4.1.9.1.2494')


class IndexSuffixTestCase(SimpleTestCase):
    def test_strips_prefix(self):
        self.assertEqual(
            index_suffix('1.3.6.1.2.1.2.2.1.2', '1.3.6.1.2.1.2.2.1.2.7'),
            [7],
        )

    def test_multi_part_suffix(self):
        self.assertEqual(
            index_suffix('1.3.6.1.2.1.4.20.1.1', '1.3.6.1.2.1.4.20.1.1.10.0.0.1'),
            [10, 0, 0, 1],
        )

    def test_unrelated_oid(self):
        self.assertEqual(index_suffix('1.3.6.1.2.1.1', '1.2.3.4'), [])


class DecodeTestCase(SimpleTestCase):
    def test_decode_text(self):
        self.assertEqual(parsers.decode_text(b'core-sw-1\x00'), 'core-sw-1')
        self.assertEqual(parsers.decode_text('already str'), 'already str')
        self.assertEqual(parsers.decode_text(None), '')

    def test_bytes_to_mac(self):
        self.assertEqual(parsers.bytes_to_mac(b'\xaa\xbb\xcc\xdd\xee\xff'), 'aa:bb:cc:dd:ee:ff')
        self.assertIsNone(parsers.bytes_to_mac(b'\x00' * 6))
        self.assertIsNone(parsers.bytes_to_mac(b'\xaa\xbb'))

    def test_bytes_to_ip(self):
        self.assertEqual(parsers.bytes_to_ip(b'\x0a\x00\x00\x01'), '10.0.0.1')
        self.assertEqual(
            parsers.bytes_to_ip(bytes.fromhex('20010db8000000000000000000000001')),
            '2001:db8::1',
        )
        self.assertIsNone(parsers.bytes_to_ip(b'\x01\x02\x03'))

    def test_octets_to_ip(self):
        self.assertEqual(parsers.octets_to_ip([10, 0, 0, 2]), '10.0.0.2')
        self.assertIsNone(parsers.octets_to_ip([10, 0, 0]))

    def test_mask_to_prefix(self):
        self.assertEqual(parsers.mask_to_prefix(b'\xff\xff\xff\x00'), 24)
        self.assertEqual(parsers.mask_to_prefix(b'\xff\xff\xff\xfc'), 30)
        self.assertIsNone(parsers.mask_to_prefix(b'\xff\x00\xff\x00'))


class PortListTestCase(SimpleTestCase):
    def test_first_octet_bits(self):
        self.assertEqual(parsers.port_list_to_ports(b'\x80'), {1})
        self.assertEqual(parsers.port_list_to_ports(b'\x40'), {2})
        self.assertEqual(parsers.port_list_to_ports(b'\xc0'), {1, 2})
        self.assertEqual(parsers.port_list_to_ports(b'\x01'), {8})

    def test_multiple_octets(self):
        self.assertEqual(parsers.port_list_to_ports(b'\x80\x80'), {1, 9})

    def test_empty(self):
        self.assertEqual(parsers.port_list_to_ports(b''), set())
        self.assertEqual(parsers.port_list_to_ports(None), set())


class MacSuffixTestCase(SimpleTestCase):
    def test_valid(self):
        self.assertEqual(
            parsers.mac_from_suffix([0, 17, 34, 51, 68, 85]),
            '00:11:22:33:44:55',
        )

    def test_invalid(self):
        self.assertIsNone(parsers.mac_from_suffix([0, 17, 34]))
        self.assertIsNone(parsers.mac_from_suffix([0, 17, 34, 51, 68, 300]))
        self.assertIsNone(parsers.mac_from_suffix(['x', 1, 2, 3, 4, 5]))


class SpeedTestCase(SimpleTestCase):
    def test_high_speed_is_preferred(self):
        self.assertEqual(parsers.speed_kbps(1000, 1000000000), 1_000_000)
        self.assertEqual(parsers.speed_bps(1000, 0), 1_000_000_000)

    def test_fallback_to_speed(self):
        self.assertEqual(parsers.speed_kbps(None, 100_000_000), 100_000)

    def test_unknown(self):
        self.assertIsNone(parsers.speed_kbps(None, None))
        self.assertEqual(parsers.speed_bps(None, None), 0)


class InterfaceTypeTestCase(SimpleTestCase):
    def test_ethernet_by_speed(self):
        self.assertEqual(
            parsers.map_interface_type(6, 100_000_000),
            InterfaceTypeChoices.TYPE_100ME_FIXED,
        )
        self.assertEqual(
            parsers.map_interface_type(6, 1_000_000_000),
            InterfaceTypeChoices.TYPE_1GE_FIXED,
        )
        self.assertEqual(
            parsers.map_interface_type(6, 10_000_000_000),
            InterfaceTypeChoices.TYPE_10GE_SFP_PLUS,
        )
        self.assertEqual(
            parsers.map_interface_type(6, 100_000_000_000),
            InterfaceTypeChoices.TYPE_100GE_QSFP28,
        )

    def test_non_ethernet(self):
        self.assertEqual(
            parsers.map_interface_type(24, 0), InterfaceTypeChoices.TYPE_VIRTUAL
        )
        self.assertEqual(parsers.map_interface_type(161, 0), InterfaceTypeChoices.TYPE_LAG)
        self.assertEqual(parsers.map_interface_type(1, 0), InterfaceTypeChoices.TYPE_OTHER)
