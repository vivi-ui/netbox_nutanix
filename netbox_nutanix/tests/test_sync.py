from django.test import SimpleTestCase, TestCase

from dcim.models import Device, Interface, Site
from ipam.models import IPAddress
from virtualization.models import ClusterType, Cluster as VirtualizationCluster, VMInterface, VirtualMachine

from netbox_nutanix.models import NutanixCluster, NutanixDisk, NutanixHost, NutanixVirtualMachine
from netbox_nutanix.sync import NutanixSynchronizer, SyncResult, map_vm_status


class SyncHelperTestCase(SimpleTestCase):
    def test_normalize_cidr(self):
        self.assertEqual(NutanixSynchronizer._normalize_cidr('10.0.0.1'), '10.0.0.1/32')
        self.assertEqual(NutanixSynchronizer._normalize_cidr('10.0.0.0/24'), '10.0.0.0/24')
        self.assertEqual(NutanixSynchronizer._normalize_cidr('fd00::1'), 'fd00::1/128')
        self.assertIsNone(NutanixSynchronizer._normalize_cidr(''))
        self.assertIsNone(NutanixSynchronizer._normalize_cidr(None))

    def test_interface_name(self):
        self.assertEqual(NutanixSynchronizer._interface_name({'name': 'eth0', 'index': 3}), 'eth0')
        self.assertEqual(NutanixSynchronizer._interface_name({'name': None, 'index': 2}), 'eth2')
        self.assertEqual(NutanixSynchronizer._interface_name({}), 'eth0')


class StatusMappingTestCase(SimpleTestCase):
    def test_on_maps_to_active(self):
        self.assertEqual(map_vm_status('on'), 'active')
        self.assertEqual(map_vm_status('POWERON'), 'active')

    def test_off_maps_to_off(self):
        self.assertEqual(map_vm_status('off'), 'off')

    def test_paused_maps_to_paused(self):
        self.assertEqual(map_vm_status('paused'), 'paused')
        self.assertEqual(map_vm_status('suspended'), 'paused')

    def test_unknown_defaults_to_off(self):
        self.assertEqual(map_vm_status(''), 'off')
        self.assertEqual(map_vm_status(None), 'off')


class SyncResultTestCase(SimpleTestCase):
    def test_summary(self):
        result = SyncResult()
        result.created = 2
        result.updated = 3
        result.deleted = 1
        result.errors = 0
        self.assertEqual(
            result.summary(),
            'created=2, updated=3, deleted=1, errors=0',
        )


class SyncReconciliationTestCase(TestCase):
    def setUp(self):
        self.site = Site.objects.create(name='Test Site', slug='test-site')
        self.endpoint = NutanixCluster(
            name='prism-central',
            base_url='https://prism.example.com:9440',
            username='admin',
            site=self.site,
        )
        self.endpoint.set_password('secret')
        self.endpoint.save()
        self.sync = NutanixSynchronizer(self.endpoint, log=lambda *a, **k: None)

    def test_sync_host_creates_device_interfaces_and_ips(self):
        data = {
            'uuid': '11111111-1111-1111-1111-111111111111',
            'name': 'node-1',
            'serial': 'SN1',
            'model': 'NX-1000',
            'interfaces': [
                {
                    'index': 0,
                    'name': 'eth0',
                    'mac_address': 'aa:bb:cc:dd:ee:ff',
                    'ip_addresses': ['10.0.0.5'],
                    'enabled': True,
                    'network_name': 'mgmt',
                },
            ],
        }
        self.sync._sync_host(data)

        device = Device.objects.get(name='node-1')
        interface = Interface.objects.get(device=device, name='eth0')
        self.assertEqual(str(interface.mac_address).lower(), 'aa:bb:cc:dd:ee:ff')
        self.assertEqual(interface.description, 'mgmt')
        self.assertTrue(
            IPAddress.objects.filter(
                address='10.0.0.5/32', assigned_object_id=interface.pk
            ).exists()
        )
        device.refresh_from_db()
        self.assertEqual(str(device.primary_ip4.address), '10.0.0.5/32')
        self.assertTrue(NutanixHost.objects.filter(uuid=data['uuid']).exists())

    def test_sync_host_creates_mgmt_interface_when_nics_missing(self):
        data = {
            'uuid': '66666666-6666-6666-6666-666666666666',
            'name': 'node-mgmt',
            'ip_address': '172.17.83.50',
            'interfaces': [],
        }
        self.sync._sync_host(data)

        device = Device.objects.get(name='node-mgmt')
        interface = Interface.objects.get(device=device, name='mgmt0')
        self.assertTrue(
            IPAddress.objects.filter(
                address='172.17.83.50/32', assigned_object_id=interface.pk
            ).exists()
        )

    def test_sync_vm_creates_interfaces_ips_and_disks(self):
        cluster_type = ClusterType.objects.create(name='Nutanix', slug='nutanix')
        self.endpoint.cluster = VirtualizationCluster.objects.create(
            name='vc-1', type=cluster_type
        )
        self.endpoint.save()

        data = {
            'uuid': '22222222-2222-2222-2222-222222222222',
            'name': 'vm-1',
            'power_state': 'on',
            'vcpus': 2,
            'memory_mb': 2048,
            'disk_gib': 10,
            'disk_mb': 10 * 1024,
            'interfaces': [
                {
                    'index': 0,
                    'name': None,
                    'mac_address': 'aa:bb:cc:00:00:01',
                    'ip_addresses': ['192.168.1.10/24'],
                    'enabled': True,
                    'network_name': 'vlan-10',
                },
            ],
            'disks': [
                {
                    'uuid': '33333333-3333-3333-3333-333333333333',
                    'device_index': 0,
                    'adapter_type': 'SCSI',
                    'size_bytes': 10 * 1024 ** 3,
                    'storage_container': 'sc-1',
                },
            ],
        }
        self.sync._sync_vm(data)

        vm = VirtualMachine.objects.get(name='vm-1')
        interface = VMInterface.objects.get(virtual_machine=vm, name='eth0')
        self.assertEqual(str(interface.mac_address).lower(), 'aa:bb:cc:00:00:01')
        self.assertTrue(IPAddress.objects.filter(assigned_object_id=interface.pk).exists())
        vm.refresh_from_db()
        self.assertEqual(str(vm.primary_ip4.address), '192.168.1.10/24')
        self.assertEqual(vm.disk, 10 * 1024)

        record = NutanixVirtualMachine.objects.get(uuid=data['uuid'])
        disk = NutanixDisk.objects.get(virtual_machine=record)
        self.assertEqual(disk.adapter_type, 'SCSI')
        self.assertEqual(disk.size_bytes, 10 * 1024 ** 3)
        self.assertEqual(disk.storage_container, 'sc-1')

    def test_sync_vm_updates_existing_disk_in_place(self):
        self.endpoint.cluster = None
        self.endpoint.save()
        data = {
            'uuid': '44444444-4444-4444-4444-444444444444',
            'name': 'vm-2',
            'power_state': 'off',
            'interfaces': [],
            'disks': [
                {'uuid': '55555555-5555-5555-5555-555555555555', 'device_index': 0,
                 'adapter_type': 'SCSI', 'size_bytes': 1024 ** 3, 'storage_container': 'a'},
            ],
        }
        self.sync._sync_vm(data)
        data['disks'][0]['size_bytes'] = 2 * 1024 ** 3
        self.sync._sync_vm(data)

        record = NutanixVirtualMachine.objects.get(uuid=data['uuid'])
        disks = NutanixDisk.objects.filter(virtual_machine=record)
        self.assertEqual(disks.count(), 1)
        self.assertEqual(disks.first().size_bytes, 2 * 1024 ** 3)
