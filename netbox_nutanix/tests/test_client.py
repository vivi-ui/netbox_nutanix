from unittest.mock import patch

from django.test import SimpleTestCase

from netbox_nutanix.nutanix.client import NutanixClient


class NormalizationTestCase(SimpleTestCase):
    def setUp(self):
        self.client = NutanixClient(
            'https://prism.example.com:9440', 'user', 'secret', deployment='pc'
        )

    def test_pc_vm_normalization(self):
        entity = {
            'metadata': {'uuid': 'vm-1'},
            'spec': {
                'name': 'web-01',
                'resources': {
                    'num_sockets': 2,
                    'num_vcpus_per_socket': 4,
                    'memory_size_mib': 8192,
                    'power_state': 'ON',
                    'disk_list': [{
                        'uuid': 'disk-1',
                        'disk_size_bytes': 20 * 1024 ** 3,
                        'device_properties': {
                            'disk_address': {'device_index': 0, 'adapter_type': 'SCSI'},
                        },
                        'storage_config': {
                            'storage_container_reference': {'name': 'default-container'},
                        },
                    }],
                    'nic_list': [{
                        'mac_address': 'AA:BB:CC:DD:EE:FF',
                        'is_connected': True,
                        'ip_endpoint_list': [{'ip': '10.0.0.10'}],
                        'subnet_reference': {'name': 'vlan-10'},
                    }],
                },
            },
            'status': {
                'resources': {'power_state': 'ON'},
                'cluster_reference': {'uuid': 'cluster-1'},
            },
        }
        vm = self.client._normalize_pc_vm(entity)
        self.assertEqual(vm['uuid'], 'vm-1')
        self.assertEqual(vm['name'], 'web-01')
        self.assertEqual(vm['vcpus'], 8)
        self.assertEqual(vm['memory_mb'], 8192)
        self.assertEqual(vm['disk_gib'], 20)
        self.assertEqual(vm['disk_mb'], 20 * 1024)
        self.assertEqual(vm['power_state'], 'on')
        self.assertEqual(vm['cluster_uuid'], 'cluster-1')
        self.assertEqual(len(vm['interfaces']), 1)
        self.assertEqual(vm['interfaces'][0]['mac_address'], 'aa:bb:cc:dd:ee:ff')
        self.assertEqual(vm['interfaces'][0]['ip_addresses'], ['10.0.0.10'])
        self.assertEqual(vm['interfaces'][0]['network_name'], 'vlan-10')
        self.assertTrue(vm['interfaces'][0]['enabled'])
        self.assertEqual(len(vm['disks']), 1)
        self.assertEqual(vm['disks'][0]['uuid'], 'disk-1')
        self.assertEqual(vm['disks'][0]['device_index'], 0)
        self.assertEqual(vm['disks'][0]['adapter_type'], 'SCSI')
        self.assertEqual(vm['disks'][0]['size_bytes'], 20 * 1024 ** 3)
        self.assertEqual(vm['disks'][0]['storage_container'], 'default-container')

    def test_pc_host_normalization(self):
        entity = {
            'metadata': {'uuid': 'host-1'},
            'spec': {'name': 'node-1', 'resources': {'serial': 'ABC123'}},
            'status': {
                'name': 'node-1',
                'resources': {'cpu_model': 'Intel Xeon', 'ip': '10.0.0.5'},
                'cluster_reference': {'uuid': 'cluster-1'},
            },
        }
        host = self.client._normalize_pc_host(entity)
        self.assertEqual(host['uuid'], 'host-1')
        self.assertEqual(host['name'], 'node-1')
        self.assertEqual(host['serial'], 'ABC123')
        self.assertEqual(host['model'], 'Intel Xeon')
        self.assertEqual(host['ip_address'], '10.0.0.5')

    def test_pc_host_normalization_fallbacks(self):
        entity = {
            'metadata': {'uuid': 'host-9'},
            'spec': {},
            'status': {
                'name': 'node-9',
                'resources': {
                    'serial_number': 'HM251S008729',
                    'host_nics_id_list': [],
                    'controller_vm': {'ip': '172.17.83.16'},
                },
                'cluster_reference': {'uuid': 'cluster-1'},
            },
        }
        host = self.client._normalize_pc_host(entity)
        self.assertEqual(host['serial'], 'HM251S008729')
        self.assertEqual(host['ip_address'], '172.17.83.16')
        self.assertEqual(host['interfaces'], [])

    def test_pe_vm_normalization(self):
        client = NutanixClient('https://pe.example.com:9440', 'u', 'p', deployment='pe')
        entity = {
            'uuid': 'vm-2',
            'name': 'db-01',
            'power_state': 'off',
            'num_vcpus': 4,
            'num_cores_per_vcpu': 2,
            'memory_mb': 16384,
            'host_uuid': 'host-2',
            'vm_disks': [{
                'disk_size_in_bytes': 50 * 1024 ** 3,
                'device_index': 1,
                'adapter_type': 'IDE',
                'vm_disk': {'storage_container_uuid': 'sc-uuid'},
            }],
            'virtual_nics': [{
                'mac_address': 'AA:BB:CC:00:11:22',
                'connected': True,
                'ip_addresses': ['192.168.1.5'],
                'vlan_id': 10,
            }],
        }
        vm = client._normalize_pe_vm(entity)
        self.assertEqual(vm['vcpus'], 8)
        self.assertEqual(vm['memory_mb'], 16384)
        self.assertEqual(vm['disk_gib'], 50)
        self.assertEqual(vm['disk_mb'], 50 * 1024)
        self.assertEqual(vm['host_uuid'], 'host-2')
        self.assertEqual(len(vm['interfaces']), 1)
        self.assertEqual(vm['interfaces'][0]['mac_address'], 'aa:bb:cc:00:11:22')
        self.assertEqual(vm['interfaces'][0]['ip_addresses'], ['192.168.1.5'])
        self.assertEqual(vm['interfaces'][0]['vlan_id'], 10)
        self.assertEqual(vm['disks'][0]['device_index'], 1)
        self.assertEqual(vm['disks'][0]['adapter_type'], 'IDE')
        self.assertEqual(vm['disks'][0]['size_bytes'], 50 * 1024 ** 3)
        self.assertEqual(vm['disks'][0]['storage_container'], 'sc-uuid')

    def test_bytes_to_gib_handles_invalid(self):
        self.assertIsNone(self.client._bytes_to_gib('not-a-number'))
        self.assertEqual(self.client._bytes_to_gib(1024 ** 3), 1)

    def test_api_roots(self):
        self.assertTrue(self.client.api_root.endswith('/api/nutanix/v3/'))
        pe_client = NutanixClient('https://pe.example.com:9440', 'u', 'p', deployment='pe')
        self.assertTrue(pe_client.api_root.endswith('/PrismGateway/services/rest/v2.0/'))

    def test_list_v3_uses_singular_kind(self):
        captured = {}

        def fake_request(method, path, **kwargs):
            captured['method'] = method
            captured['path'] = path
            captured['json'] = kwargs.get('json')
            return {'entities': [], 'metadata': {'total_matches': 0}}

        with patch.object(self.client, '_request', side_effect=fake_request):
            self.client.list_hosts()

        self.assertEqual(captured['method'], 'POST')
        self.assertEqual(captured['path'], 'hosts/list')
        self.assertEqual(captured['json']['kind'], 'host')
        self.assertEqual(captured['json']['length'], 500)

    def test_normalize_interfaces_prefers_named_nics(self):
        interfaces = NutanixClient._normalize_interfaces({
            'nic_list': [
                {'name': 'eth0', 'mac_address': 'AA:BB:CC:DD:EE:01',
                 'ip_endpoint_list': [{'ip': '10.0.0.1'}, {'ip': '10.0.0.2'}]},
                {'mac_address': 'AA:BB:CC:DD:EE:02'},
            ],
        })
        self.assertEqual(interfaces[0]['name'], 'eth0')
        self.assertEqual(interfaces[0]['index'], 0)
        self.assertEqual(interfaces[0]['ip_addresses'], ['10.0.0.1', '10.0.0.2'])
        self.assertIsNone(interfaces[1]['name'])
        self.assertEqual(interfaces[1]['index'], 1)

    def test_normalize_interfaces_pe_aliases(self):
        interfaces = NutanixClient._normalize_interfaces({
            'nics': [{'mac_address': 'AA:BB:CC:DD:EE:03', 'connected': False,
                      'ip_addresses': ['172.16.0.9']}],
        })
        self.assertEqual(len(interfaces), 1)
        self.assertFalse(interfaces[0]['enabled'])
        self.assertEqual(interfaces[0]['ip_addresses'], ['172.16.0.9'])

    def test_normalize_disks_pe_nested(self):
        disks = NutanixClient._normalize_disks({
            'vm_disks': [{'vm_disk': {'disk_size_in_bytes': 2 * 1024 ** 3,
                                      'storage_container_uuid': 'sc-1'}}],
        })
        self.assertEqual(len(disks), 1)
        self.assertEqual(disks[0]['size_bytes'], 2 * 1024 ** 3)
        self.assertEqual(disks[0]['storage_container'], 'sc-1')
        self.assertEqual(disks[0]['device_index'], 0)

    def test_normalize_disks_handles_mib(self):
        disks = NutanixClient._normalize_disks({
            'disk_list': [{'disk_size_mib': 1024}],
        })
        self.assertEqual(disks[0]['size_bytes'], 1024 * 1024 * 1024)

    def test_normalize_disks_skips_cdrom_and_volume_groups(self):
        disks = NutanixClient._normalize_disks({
            'disk_list': [
                {
                    'uuid': 'disk-1',
                    'disk_size_bytes': 50 * 1024 ** 3,
                    'device_properties': {
                        'device_type': 'DISK',
                        'disk_address': {'device_index': 0, 'adapter_type': 'SCSI'},
                    },
                },
                {
                    'uuid': 'cdrom-1',
                    'device_properties': {
                        'device_type': 'CDROM',
                        'disk_address': {'device_index': 0, 'adapter_type': 'SATA'},
                    },
                },
                {
                    'uuid': 'vg-1',
                    'device_properties': {
                        'device_type': 'VOLUME_GROUP',
                        'disk_address': {'device_index': 1, 'adapter_type': 'SCSI'},
                    },
                },
            ],
        })
        self.assertEqual(len(disks), 1)
        self.assertEqual(disks[0]['uuid'], 'disk-1')
        self.assertEqual(disks[0]['device_index'], 0)

    def test_normalize_disks_skips_pe_cdrom(self):
        disks = NutanixClient._normalize_disks({
            'vm_disks': [
                {'is_cdrom': True, 'disk_address': {'device_index': 0}},
                {'disk_size_in_bytes': 2 * 1024 ** 3},
            ],
        })
        self.assertEqual(len(disks), 1)
        self.assertEqual(disks[0]['size_bytes'], 2 * 1024 ** 3)
