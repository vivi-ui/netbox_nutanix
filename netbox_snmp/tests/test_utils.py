from django.test import SimpleTestCase

from netbox_snmp.utils import parse_target_addresses


class ParseTargetAddressesTestCase(SimpleTestCase):
    def test_single_address(self):
        self.assertEqual(parse_target_addresses('10.0.0.1'), (['10.0.0.1'], []))

    def test_network_is_normalized(self):
        self.assertEqual(parse_target_addresses('10.0.0.5/24'), (['10.0.0.0/24'], []))

    def test_multiple_separators(self):
        valid, invalid = parse_target_addresses('10.0.0.1, 10.0.0.0/24\n192.168.1.0/28; 10.0.0.1')
        self.assertEqual(
            valid,
            ['10.0.0.1', '10.0.0.0/24', '192.168.1.0/28'],
        )
        self.assertEqual(invalid, [])

    def test_invalid_entries_reported(self):
        valid, invalid = parse_target_addresses('10.0.0.1 bogus 999.1.1.1')
        self.assertEqual(valid, ['10.0.0.1'])
        self.assertEqual(invalid, ['bogus', '999.1.1.1'])

    def test_ipv6(self):
        valid, invalid = parse_target_addresses('2001:db8::1\n2001:db8::/32')
        self.assertEqual(valid, ['2001:db8::1', '2001:db8::/32'])
        self.assertEqual(invalid, [])

    def test_empty(self):
        self.assertEqual(parse_target_addresses(''), ([], []))
        self.assertEqual(parse_target_addresses(None), ([], []))
