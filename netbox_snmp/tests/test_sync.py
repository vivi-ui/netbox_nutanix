from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from dcim.choices import InterfaceModeChoices, InterfaceTypeChoices
from dcim.models import Cable, Device, Manufacturer, Site
from ipam.choices import IPAddressStatusChoices
from ipam.models import IPAddress, Prefix, VLAN

from netbox_snmp.exceptions import SyncCancelled
from netbox_snmp.models import SnmpDevice, SnmpEndpoint, SnmpTarget
from netbox_snmp.snmp import oids
from netbox_snmp.sync import SnmpSynchronizer, SyncResult, run_sync, vendor_name

SYSTEM = {
    'sys_descr': b'Test switch, version 1.0',
    'sys_object_id': '1.3.6.1.4.1.9.1.2494',
    'sys_name': b'core-sw-1',
    'sys_contact': b'',
    'sys_location': b'DC1',
    'sys_uptime': 1234500,
}

INTERFACE_COLUMNS = {
    oids.IF_NAME: {'1.3.6.1.2.1.31.1.1.1.1.1': b'Gi0/1'},
    oids.IF_DESCR: {'1.3.6.1.2.1.2.2.1.2.1': b'GigabitEthernet0/1'},
    oids.IF_TYPE: {'1.3.6.1.2.1.2.2.1.3.1': 6},
    oids.IF_HIGH_SPEED: {'1.3.6.1.2.1.31.1.1.1.15.1': 1000},
    oids.IF_PHYS_ADDRESS: {'1.3.6.1.2.1.2.2.1.6.1': b'\xaa\xbb\xcc\xdd\xee\xff'},
    oids.IF_ADMIN_STATUS: {'1.3.6.1.2.1.2.2.1.7.1': 1},
    oids.IF_ALIAS: {'1.3.6.1.2.1.31.1.1.1.18.1': b'uplink to core'},
    oids.IF_MTU: {'1.3.6.1.2.1.2.2.1.4.1': 1500},
    oids.IP_AD_ENT_ADDR: {'1.3.6.1.2.1.4.20.1.1.10.0.0.1': b'\x0a\x00\x00\x01'},
    oids.IP_AD_ENT_IF_INDEX: {'1.3.6.1.2.1.4.20.1.2.10.0.0.1': 1},
    oids.IP_AD_ENT_NET_MASK: {'1.3.6.1.2.1.4.20.1.3.10.0.0.1': b'\xff\xff\xff\x00'},
}


class FakeClient:
    def __init__(self, host, system=None, columns=None):
        self.host = host
        self._system = system or {}
        self._columns = columns or {}

    def get_system(self):
        return self._system

    def walk(self, oid, max_rows=None):
        return self._columns.get(oid, {})


class VendorTestCase(SimpleTestCase):
    def test_known_vendor(self):
        self.assertEqual(vendor_name('1.3.6.1.4.1.9.1.2494'), 'Cisco')
        self.assertEqual(vendor_name('1.3.6.1.4.1.2636.1.1.1.2.1'), 'Juniper')

    def test_unknown_vendor(self):
        self.assertIsNone(vendor_name('1.3.6.1.4.1.999999.1'))
        self.assertIsNone(vendor_name(''))
        self.assertIsNone(vendor_name(None))


class SyncResultTestCase(SimpleTestCase):
    def test_summary(self):
        result = SyncResult()
        result.created = 1
        result.updated = 2
        result.deleted = 3
        result.cables = 5
        result.errors = 4
        self.assertEqual(
            result.summary(),
            'created=1, updated=2, deleted=3, cables=5, errors=4',
        )


class ExpandTargetTestCase(TestCase):
    def setUp(self):
        site = Site.objects.create(name='Test Site', slug='test-site')
        self.endpoint = SnmpEndpoint.objects.create(name='snmp-1', site=site)
        self.sync = SnmpSynchronizer(self.endpoint, log=lambda *a, **k: None)

    def test_plain_address(self):
        self.assertEqual(list(self.sync._expand_target('10.0.0.5')), ['10.0.0.5'])

    def test_cidr(self):
        self.assertEqual(
            list(self.sync._expand_target('10.0.0.0/30')),
            ['10.0.0.1', '10.0.0.2'],
        )

    def test_invalid(self):
        self.assertEqual(list(self.sync._expand_target('not-an-address')), [])


class SyncDeviceTestCase(TestCase):
    def setUp(self):
        self.site = Site.objects.create(name='Test Site', slug='test-site')
        self.endpoint = SnmpEndpoint.objects.create(name='snmp-1', site=self.site)
        self.sync = SnmpSynchronizer(self.endpoint, log=lambda *a, **k: None)

    def _client(self, host='10.0.0.1', system=None, columns=None):
        return FakeClient(host, system or dict(SYSTEM), columns or dict(INTERFACE_COLUMNS))

    def test_sync_device_creates_device_interface_ip_and_mac(self):
        with patch.object(self.sync, '_client_for', return_value=self._client()):
            self.sync._sync_device('10.0.0.1')

        device = Device.objects.get(name='core-sw-1')
        self.assertEqual(device.site, self.site)
        self.assertEqual(device.device_type.manufacturer.name, 'Cisco')

        interface = device.interfaces.get(name='Gi0/1')
        self.assertEqual(interface.type, InterfaceTypeChoices.TYPE_1GE_FIXED)
        self.assertEqual(interface.speed, 1_000_000)
        self.assertEqual(interface.mtu, 1500)
        self.assertEqual(interface.description, 'uplink to core')
        self.assertEqual(str(interface.mac_address).lower(), 'aa:bb:cc:dd:ee:ff')

        ip = IPAddress.objects.get(address='10.0.0.1/24')
        self.assertEqual(ip.assigned_object_id, interface.pk)

        device.refresh_from_db()
        self.assertEqual(str(device.primary_ip4.address), '10.0.0.1/24')

        record = SnmpDevice.objects.get(endpoint=self.endpoint, address='10.0.0.1')
        self.assertEqual(record.netbox_device, device)
        self.assertEqual(record.sys_location, 'DC1')

    def test_serial_from_entity_mib(self):
        columns = dict(INTERFACE_COLUMNS)
        columns[oids.ENT_PHYSICAL_CLASS] = {'1.3.6.1.2.1.47.1.1.1.1.5.1': 3}
        columns[oids.ENT_PHYSICAL_SERIAL_NUM] = {'1.3.6.1.2.1.47.1.1.1.1.11.1': b'SERIAL123'}
        with patch.object(self.sync, '_client_for', return_value=self._client(columns=columns)):
            self.sync._sync_device('10.0.0.1')

        device = Device.objects.get(name='core-sw-1')
        self.assertEqual(device.serial, 'SERIAL123')

    def test_neighbors_from_lldp_and_cdp(self):
        columns = {
            oids.LLDP_REM_MAN_ADDR_IF_ID: {
                '1.0.8802.1.1.2.1.4.2.1.3.0.2.1.1.4.10.0.0.2': 1,
            },
            oids.CDP_CACHE_ADDRESS: {
                '1.3.6.1.4.1.9.9.23.1.2.1.1.4.1.1': b'\x0a\x00\x00\x03',
            },
        }
        addresses, links = self.sync._collect_neighbors(self._client(columns=columns))
        self.assertEqual(addresses, {'10.0.0.2', '10.0.0.3'})

    def test_neighbors_ignore_link_local_and_loopback(self):
        columns = {
            oids.CDP_CACHE_ADDRESS: {
                '1.3.6.1.4.1.9.9.23.1.2.1.1.4.1.1': b'\x7f\x00\x00\x01',
                '1.3.6.1.4.1.9.9.23.1.2.1.1.4.1.2': b'\xa9\xfe\x01\x01',
            },
        }
        addresses, links = self.sync._collect_neighbors(self._client(columns=columns))
        self.assertEqual(addresses, set())
        self.assertEqual(links, [])

    def test_lldp_link_details(self):
        columns = {
            oids.LLDP_REM_PORT_ID: {
                '1.0.8802.1.1.2.1.4.1.1.7.0.1.1': b'GigabitEthernet0/2',
            },
            oids.LLDP_REM_PORT_DESC: {
                '1.0.8802.1.1.2.1.4.1.1.8.0.1.1': b'GigabitEthernet0/2',
            },
            oids.LLDP_REM_SYS_NAME: {
                '1.0.8802.1.1.2.1.4.1.1.9.0.1.1': b'edge-sw-2',
            },
            oids.LLDP_REM_CHASSIS_ID: {
                '1.0.8802.1.1.2.1.4.1.1.5.0.1.1': b'\x00\x11\x22\x33\x44\x55',
            },
            oids.LLDP_REM_MAN_ADDR_IF_ID: {
                '1.0.8802.1.1.2.1.4.2.1.3.0.1.1.1.4.10.0.0.2': 1,
            },
        }
        addresses, links = self.sync._collect_neighbors(self._client(columns=columns))
        self.assertEqual(addresses, {'10.0.0.2'})
        self.assertEqual(len(links), 1)
        link = links[0]
        self.assertEqual(link.local_index, 1)
        self.assertEqual(link.remote_port_id, 'GigabitEthernet0/2')
        self.assertEqual(link.remote_sys_name, 'edge-sw-2')
        self.assertEqual(link.remote_chassis_id, '00:11:22:33:44:55')
        self.assertEqual(link.remote_addresses, {'10.0.0.2'})

    def test_run_follows_neighbors(self):
        SnmpTarget.objects.create(endpoint=self.endpoint, address='10.0.0.1')

        neighbor_columns = dict(INTERFACE_COLUMNS)
        neighbor_columns[oids.LLDP_REM_MAN_ADDR_IF_ID] = {
            '1.0.8802.1.1.2.1.4.2.1.3.0.2.1.1.4.10.0.0.2': 1,
        }
        second_system = dict(SYSTEM)
        second_system['sys_name'] = b'edge-sw-2'

        def fake_client_for(address, **kwargs):
            if address == '10.0.0.2':
                return FakeClient(address, system=second_system, columns={})
            return FakeClient(address, system=dict(SYSTEM), columns=neighbor_columns)

        with patch.object(self.sync, '_client_for', side_effect=fake_client_for):
            result = self.sync.run()

        self.assertEqual(result.discovered, 2)
        self.assertEqual(SnmpDevice.objects.count(), 2)
        self.assertTrue(Device.objects.filter(name='edge-sw-2').exists())

    def test_prune_removes_unseen_devices(self):
        seen = SnmpDevice.objects.create(endpoint=self.endpoint, address='10.0.0.1')
        stale = SnmpDevice.objects.create(endpoint=self.endpoint, address='10.0.0.9')

        self.sync._prune({'10.0.0.1'})

        self.assertTrue(SnmpDevice.objects.filter(pk=seen.pk).exists())
        self.assertFalse(SnmpDevice.objects.filter(pk=stale.pk).exists())
        self.assertEqual(self.sync.result.deleted, 1)


class CableTestCase(TestCase):
    def setUp(self):
        self.site = Site.objects.create(name='Cable Site', slug='cable-site')
        self.endpoint = SnmpEndpoint.objects.create(
            name='snmp-cable', site=self.site, create_cables=True, max_depth=1
        )
        self.sync = SnmpSynchronizer(self.endpoint, log=lambda *a, **k: None)
        SnmpTarget.objects.create(endpoint=self.endpoint, address='10.0.0.1')

    @staticmethod
    def _columns(port):
        columns = dict(INTERFACE_COLUMNS)
        columns[oids.IF_NAME] = {'1.3.6.1.2.1.31.1.1.1.1.1': port.encode()}
        columns[oids.IF_DESCR] = {'1.3.6.1.2.1.2.2.1.2.1': port.encode()}
        return columns

    def _fake_client_for(self, local_columns, remote_columns):
        local_system = dict(SYSTEM)
        local_system['sys_name'] = b'core-sw-1'
        remote_system = dict(SYSTEM)
        remote_system['sys_name'] = b'edge-sw-2'

        def fake_client_for(address, **kwargs):
            if address == '10.0.0.2':
                return FakeClient(address, system=remote_system, columns=remote_columns)
            return FakeClient(address, system=local_system, columns=local_columns)

        return fake_client_for

    def _local_columns_with_link(self):
        columns = self._columns('Gi0/1')
        columns[oids.LLDP_REM_PORT_ID] = {'1.0.8802.1.1.2.1.4.1.1.7.0.1.1': b'Gi0/2'}
        columns[oids.LLDP_REM_SYS_NAME] = {'1.0.8802.1.1.2.1.4.1.1.9.0.1.1': b'edge-sw-2'}
        columns[oids.LLDP_REM_MAN_ADDR_IF_ID] = {
            '1.0.8802.1.1.2.1.4.2.1.3.0.1.1.1.4.10.0.0.2': 1,
        }
        return columns

    def test_run_creates_cable_from_lldp(self):
        client_for = self._fake_client_for(
            self._local_columns_with_link(), self._columns('Gi0/2')
        )
        with patch.object(SnmpSynchronizer, '_client_for', side_effect=client_for):
            result = run_sync(self.endpoint, log=lambda *a, **k: None)

        self.assertEqual(result.cables, 1)
        self.assertEqual(Cable.objects.count(), 1)
        cable = Cable.objects.get()
        peers = {
            (term.termination.device.name, term.termination.name)
            for term in cable.terminations.all()
        }
        self.assertEqual(peers, {('core-sw-1', 'Gi0/1'), ('edge-sw-2', 'Gi0/2')})

    def test_run_does_not_duplicate_cable(self):
        client_for = self._fake_client_for(
            self._local_columns_with_link(), self._columns('Gi0/2')
        )
        with patch.object(SnmpSynchronizer, '_client_for', side_effect=client_for):
            run_sync(self.endpoint, log=lambda *a, **k: None)
            second = run_sync(self.endpoint, log=lambda *a, **k: None)

        self.assertEqual(second.cables, 0)
        self.assertEqual(Cable.objects.count(), 1)


class CancellationTestCase(TestCase):
    def setUp(self):
        self.site = Site.objects.create(name='Cancel Site', slug='cancel-site')
        self.endpoint = SnmpEndpoint.objects.create(name='snmp-cancel', site=self.site)
        self.sync = SnmpSynchronizer(self.endpoint, log=lambda *a, **k: None)

    def test_should_stop_defaults_to_false_without_check(self):
        self.assertFalse(self.sync._should_stop())

    def test_run_stops_before_any_device(self):
        SnmpTarget.objects.create(endpoint=self.endpoint, address='10.0.0.1')
        result = run_sync(
            self.endpoint, log=lambda *a, **k: None, cancel_check=lambda: True
        )
        self.assertTrue(result.cancelled)
        self.assertEqual(result.discovered, 0)
        self.assertFalse(SnmpDevice.objects.filter(endpoint=self.endpoint).exists())

    def test_sync_device_aborts_before_writing(self):
        sync = SnmpSynchronizer(
            self.endpoint, log=lambda *a, **k: None, cancel_check=lambda: True
        )
        client = FakeClient('10.0.0.1', system=dict(SYSTEM), columns=dict(INTERFACE_COLUMNS))
        with patch.object(sync, '_client_for', return_value=client):
            with self.assertRaises(SyncCancelled):
                sync._sync_device('10.0.0.1')

        self.assertFalse(Device.objects.filter(name='core-sw-1').exists())
        self.assertFalse(SnmpDevice.objects.filter(endpoint=self.endpoint).exists())

    def test_summary_marks_cancelled(self):
        result = SyncResult()
        result.cancelled = True
        self.assertIn('cancelled', result.summary())


class VlanCollectionTestCase(TestCase):
    def setUp(self):
        self.site = Site.objects.create(name='VLAN Site', slug='vlan-site')
        self.endpoint = SnmpEndpoint.objects.create(
            name='snmp-vlan', site=self.site, collect_vlans=True, infer_prefixes=True
        )
        self.sync = SnmpSynchronizer(self.endpoint, log=lambda *a, **k: None)

    @staticmethod
    def _columns():
        columns = dict(INTERFACE_COLUMNS)
        columns[oids.IF_NAME] = {'1.3.6.1.2.1.31.1.1.1.1.1': b'Vlan100'}
        columns[oids.IF_DESCR] = {'1.3.6.1.2.1.2.2.1.2.1': b'Vlan100'}
        columns[oids.DOT1D_BASE_PORT_IF_INDEX] = {'1.3.6.1.2.1.17.1.4.1.2.1': 1}
        columns[oids.DOT1Q_VLAN_STATIC_NAME] = {'1.3.6.1.2.1.17.7.1.4.3.1.1.100': b'users'}
        columns[oids.DOT1Q_VLAN_STATIC_UNTAGGED] = {'1.3.6.1.2.1.17.7.1.4.3.1.4.100': b'\x80'}
        columns[oids.DOT1Q_VLAN_STATIC_EGRESS] = {'1.3.6.1.2.1.17.7.1.4.3.1.2.100': b'\xc0'}
        return columns

    def _run(self):
        client = FakeClient('10.0.0.1', system=dict(SYSTEM), columns=self._columns())
        with patch.object(self.sync, '_client_for', return_value=client):
            self.sync._sync_device('10.0.0.1')

    def test_collects_vlan_and_interface_membership(self):
        self._run()
        vlan = VLAN.objects.get(vid=100)
        self.assertEqual(vlan.name, 'users')
        self.assertEqual(vlan.site, self.site)
        interface = Device.objects.get(name='core-sw-1').interfaces.get(name='Vlan100')
        self.assertEqual(interface.untagged_vlan, vlan)
        self.assertEqual(interface.mode, InterfaceModeChoices.MODE_ACCESS)

    def test_infers_prefix_from_svi(self):
        self._run()
        prefix = Prefix.objects.get(prefix='10.0.0.0/24')
        self.assertEqual(prefix.vlan.vid, 100)
        self.assertEqual(prefix.scope, self.site)


class ArpCollectionTestCase(TestCase):
    def setUp(self):
        self.site = Site.objects.create(name='ARP Site', slug='arp-site')
        self.endpoint = SnmpEndpoint.objects.create(
            name='snmp-arp', site=self.site, collect_arp=True, collect_fdb=True
        )
        self.sync = SnmpSynchronizer(self.endpoint, log=lambda *a, **k: None)

    @staticmethod
    def _columns():
        columns = dict(INTERFACE_COLUMNS)
        columns[oids.DOT1D_BASE_PORT_IF_INDEX] = {'1.3.6.1.2.1.17.1.4.1.2.1': 1}
        columns[oids.DOT1D_TP_FDB_PORT] = {
            '1.3.6.1.2.1.17.4.3.1.2.170.187.204.221.238.1': 1,
        }
        columns[oids.IP_NET_TO_MEDIA_PHYS_ADDRESS] = {
            '1.3.6.1.2.1.4.22.1.2.1.10.0.0.5': b'\xaa\xbb\xcc\xdd\xee\x01',
        }
        return columns

    def test_collects_arp_entry(self):
        client = FakeClient('10.0.0.1', system=dict(SYSTEM), columns=self._columns())
        with patch.object(self.sync, '_client_for', return_value=client):
            self.sync._sync_device('10.0.0.1')

        interface = Device.objects.get(name='core-sw-1').interfaces.get(name='Gi0/1')
        ip = IPAddress.objects.get(address='10.0.0.5/32')
        self.assertEqual(ip.assigned_object_id, interface.pk)
        self.assertEqual(ip.status, IPAddressStatusChoices.STATUS_ACTIVE)

    def test_max_arp_entries_limits(self):
        self.endpoint.max_arp_entries = 1
        self.endpoint.save()
        columns = self._columns()
        columns[oids.IP_NET_TO_MEDIA_PHYS_ADDRESS] = {
            '1.3.6.1.2.1.4.22.1.2.1.10.0.0.5': b'\xaa\xbb\xcc\xdd\xee\x01',
            '1.3.6.1.2.1.4.22.1.2.1.10.0.0.6': b'\xaa\xbb\xcc\xdd\xee\x02',
        }
        client = FakeClient('10.0.0.1', system=dict(SYSTEM), columns=columns)
        with patch.object(self.sync, '_client_for', return_value=client):
            self.sync._sync_device('10.0.0.1')

        self.assertEqual(IPAddress.objects.filter(address__endswith='/32').count(), 1)
