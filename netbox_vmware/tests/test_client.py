from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from netbox_vmware.exceptions import VMwareAPIError, VMwareAuthError
from netbox_vmware.vmware.client import VMwareClient


class ApiRootTestCase(SimpleTestCase):
    def test_api_root(self):
        client = VMwareClient('https://vcenter.example.com/', 'u', 'p')
        self.assertEqual(client.api_root, 'https://vcenter.example.com/api')


class SessionTestCase(SimpleTestCase):
    def setUp(self):
        self.client = VMwareClient('https://vcenter.example.com', 'u', 'p')

    def test_login_stores_session_id(self):
        response = MagicMock(status_code=200)
        response.json.return_value = 'session-abc'
        with patch.object(self.client.session, 'post', return_value=response) as post:
            session_id = self.client.login()

        self.assertEqual(session_id, 'session-abc')
        self.assertEqual(self.client._session_id, 'session-abc')
        self.assertEqual(
            self.client.session.headers['vmware-api-session-id'], 'session-abc'
        )
        self.assertEqual(post.call_args.kwargs['auth'], ('u', 'p'))

    def test_login_raises_on_auth_failure(self):
        response = MagicMock(status_code=401)
        with patch.object(self.client.session, 'post', return_value=response):
            with self.assertRaises(VMwareAuthError):
                self.client.login()

    def test_login_raises_on_server_error(self):
        response = MagicMock(status_code=500, text='boom')
        with patch.object(self.client.session, 'post', return_value=response):
            with self.assertRaises(VMwareAPIError):
                self.client.login()

    def test_logout_clears_session(self):
        self.client._session_id = 'session-abc'
        self.client.session.headers['vmware-api-session-id'] = 'session-abc'
        with patch.object(self.client.session, 'delete', return_value=MagicMock(status_code=200)):
            self.client.logout()
        self.assertIsNone(self.client._session_id)
        self.assertNotIn('vmware-api-session-id', self.client.session.headers)

    def test_request_reauthenticates_once_on_401(self):
        first = MagicMock(status_code=401, text='')
        second = MagicMock(status_code=200, text='{"ok": true}')
        second.json.return_value = {'ok': True}

        self.client._session_id = 'expired-session'
        with patch.object(self.client.session, 'request', side_effect=[first, second]):
            with patch.object(self.client, 'login') as login:
                result = self.client._request('GET', 'vcenter/host')

        self.assertEqual(result, {'ok': True})
        login.assert_called_once()

    def test_request_raises_on_error_status(self):
        response = MagicMock(status_code=404, text='missing')
        self.client._session_id = 'session-abc'
        with patch.object(self.client.session, 'request', return_value=response):
            with self.assertRaises(VMwareAPIError):
                self.client._request('GET', 'vcenter/vm/bogus')


class NormalizationTestCase(SimpleTestCase):
    def setUp(self):
        self.client = VMwareClient('https://vcenter.example.com', 'user', 'secret')

    def test_power_normalization(self):
        self.assertEqual(self.client._normalize_power('POWERED_ON'), 'on')
        self.assertEqual(self.client._normalize_power('powered_off'), 'off')
        self.assertEqual(self.client._normalize_power('SUSPENDED'), 'suspended')
        self.assertEqual(self.client._normalize_power('mystery'), 'unknown')

    def test_bytes_to_gib_handles_invalid(self):
        self.assertIsNone(self.client._bytes_to_gib('not-a-number'))
        self.assertEqual(self.client._bytes_to_gib(1024 ** 3), 1)

    def test_datastore_from_backing(self):
        self.assertEqual(
            self.client._datastore_from_backing({'vmdk_file': '[datastore1] vm/disk.vmdk'}),
            'datastore1',
        )
        self.assertIsNone(self.client._datastore_from_backing({'vmdk_file': 'disk.vmdk'}))
        self.assertIsNone(self.client._datastore_from_backing(None))

    def test_normalize_disk(self):
        entry = {
            'disk': 'disk-1',
            'label': 'Hard disk 1',
            'type': 'SCSI',
            'capacity': 20 * 1024 ** 3,
            'backing': {'vmdk_file': '[datastore1] web-01/web-01.vmdk'},
        }
        disk = self.client._normalize_disk(entry, index=5)
        self.assertEqual(disk['uuid'], 'disk-1')
        self.assertEqual(disk['device_index'], 0)
        self.assertEqual(disk['adapter_type'], 'SCSI')
        self.assertEqual(disk['size_bytes'], 20 * 1024 ** 3)
        self.assertEqual(disk['storage_container'], 'datastore1')

    def test_normalize_disk_without_label_uses_index(self):
        disk = self.client._normalize_disk({'disk': 'disk-2'}, index=3)
        self.assertEqual(disk['uuid'], 'disk-2')
        self.assertEqual(disk['device_index'], 3)
        self.assertIsNone(disk['size_bytes'])

    def test_guest_address_map(self):
        mapping = self.client._guest_address_map([
            {
                'mac_address': '00:50:56:AA:BB:CC',
                'ip': {'ip_addresses': ['10.0.0.10'], 'prefix_length': 24},
            },
            {'mac_address': '00:50:56:AA:BB:DD', 'ip': {'ip_addresses': []}},
        ])
        self.assertEqual(mapping, {'00:50:56:aa:bb:cc': ['10.0.0.10/24']})

    def test_normalize_ethernet(self):
        guest = {'00:50:56:aa:bb:cc': ['10.0.0.10/24']}
        nic = {
            'label': 'Network adapter 1',
            'mac_address': '00:50:56:AA:BB:CC',
            'state': 'CONNECTED',
            'backing': {'network_name': 'VM Network'},
        }
        result = self.client._normalize_ethernet(nic, index=0, guest_addresses=guest)
        self.assertEqual(result['index'], 0)
        self.assertEqual(result['mac_address'], '00:50:56:aa:bb:cc')
        self.assertEqual(result['ip_addresses'], ['10.0.0.10/24'])
        self.assertEqual(result['network_name'], 'VM Network')
        self.assertTrue(result['enabled'])

    def test_normalize_vm(self):
        summary = {
            'vm': 'vm-1',
            'name': 'web-01',
            'power_state': 'POWERED_ON',
            'cpu_count': 2,
            'memory_size_MiB': 8192,
        }
        detail = {
            'vm': 'vm-1',
            'name': 'web-01',
            'power_state': 'POWERED_ON',
            'identity': {'instance_uuid': '52aa11bb-0000-0000-0000-000000000001'},
            'cpu': {'count': 2},
            'memory': {'size_MiB': 8192},
        }
        disks = [{
            'disk': 'disk-1',
            'label': 'Hard disk 1',
            'type': 'SCSI',
            'capacity': 20 * 1024 ** 3,
            'backing': {'vmdk_file': '[datastore1] web-01/web-01.vmdk'},
        }]
        ethernet = [{
            'mac_address': '00:50:56:AA:BB:CC',
            'state': 'CONNECTED',
            'backing': {'network_name': 'VM Network'},
        }]
        guest = [{
            'mac_address': '00:50:56:aa:bb:cc',
            'ip': {'ip_addresses': ['10.0.0.10'], 'prefix_length': 24},
        }]

        vm = self.client._normalize_vm(summary, detail, disks, ethernet, guest)
        self.assertEqual(vm['uuid'], '52aa11bb-0000-0000-0000-000000000001')
        self.assertEqual(vm['name'], 'web-01')
        self.assertEqual(vm['vcpus'], 2)
        self.assertEqual(vm['memory_mb'], 8192)
        self.assertEqual(vm['disk_gib'], 20)
        self.assertEqual(vm['disk_mb'], 20 * 1024)
        self.assertEqual(vm['power_state'], 'on')
        self.assertIsNone(vm['host_uuid'])
        self.assertEqual(len(vm['interfaces']), 1)
        self.assertEqual(vm['interfaces'][0]['network_name'], 'VM Network')
        self.assertEqual(len(vm['disks']), 1)
        self.assertEqual(vm['disks'][0]['uuid'], 'disk-1')
        self.assertEqual(vm['disks'][0]['storage_container'], 'datastore1')

    def test_normalize_vm_falls_back_to_summary(self):
        summary = {
            'vm': 'vm-2',
            'name': 'db-01',
            'power_state': 'POWERED_OFF',
            'cpu_count': 4,
            'memory_size_MiB': 16384,
        }
        vm = self.client._normalize_vm(summary, {}, [], [], [])
        self.assertEqual(vm['uuid'], 'vm-2')
        self.assertEqual(vm['vcpus'], 4)
        self.assertEqual(vm['memory_mb'], 16384)
        self.assertEqual(vm['power_state'], 'off')
        self.assertIsNone(vm['disk_gib'])
        self.assertEqual(vm['interfaces'], [])
        self.assertEqual(vm['disks'], [])

    def test_normalize_host(self):
        host = self.client._normalize_host({
            'host': 'host-1',
            'name': 'esxi01.example.com',
            'connection_state': 'CONNECTED',
        })
        self.assertEqual(host['uuid'], 'host-1')
        self.assertEqual(host['name'], 'esxi01.example.com')
        self.assertEqual(host['model'], 'VMware ESXi')
        self.assertIsNone(host['ip_address'])

    def test_normalize_host_with_ip_name(self):
        host = self.client._normalize_host({'host': 'host-2', 'name': '10.0.0.5'})
        self.assertEqual(host['ip_address'], '10.0.0.5')

    def test_normalize_standalone_host(self):
        client = VMwareClient('https://10.0.0.9', 'u', 'p', deployment='esxi')
        host = client._normalize_standalone_host()
        self.assertEqual(host['name'], '10.0.0.9')
        self.assertEqual(host['ip_address'], '10.0.0.9')
        self.assertEqual(host['model'], 'VMware ESXi')


class ListApiTestCase(SimpleTestCase):
    def setUp(self):
        self.client = VMwareClient('https://vcenter.example.com', 'u', 'p')

    def test_list_hosts(self):
        captured = {}

        def fake_request(method, path, **kwargs):
            captured['method'] = method
            captured['path'] = path
            return [{'host': 'host-1', 'name': 'esxi01.example.com'}]

        with patch.object(self.client, '_request', side_effect=fake_request):
            hosts = self.client.list_hosts()

        self.assertEqual(captured['method'], 'GET')
        self.assertEqual(captured['path'], 'vcenter/host')
        self.assertEqual(hosts[0]['uuid'], 'host-1')

    def test_list_hosts_esxi_fallback(self):
        client = VMwareClient('https://10.0.0.9', 'u', 'p', deployment='esxi')
        with patch.object(client, '_request', side_effect=VMwareAPIError('nope')):
            hosts = client.list_hosts()
        self.assertEqual(len(hosts), 1)
        self.assertEqual(hosts[0]['name'], '10.0.0.9')

    def test_list_vms_aggregates_detail_and_hardware(self):
        def fake_request(method, path, **kwargs):
            if path == 'vcenter/vm':
                return [{'vm': 'vm-1', 'name': 'web-01'}]
            if path == 'vcenter/vm/vm-1':
                return {
                    'vm': 'vm-1',
                    'name': 'web-01',
                    'power_state': 'POWERED_ON',
                    'identity': {'instance_uuid': 'uuid-1'},
                    'cpu': {'count': 2},
                    'memory': {'size_MiB': 2048},
                }
            if path == 'vcenter/vm/vm-1/hardware/disk':
                return [{
                    'disk': 'disk-1',
                    'label': 'Hard disk 1',
                    'type': 'SCSI',
                    'capacity': 1024 ** 3,
                    'backing': {'vmdk_file': '[ds1] web-01/disk.vmdk'},
                }]
            if path == 'vcenter/vm/vm-1/hardware/ethernet':
                return [{'mac_address': '00:50:56:00:00:01', 'state': 'CONNECTED'}]
            if path == 'vcenter/vm/vm-1/guest/networking/interfaces':
                return [{
                    'mac_address': '00:50:56:00:00:01',
                    'ip': {'ip_addresses': ['192.168.1.10'], 'prefix_length': 24},
                }]
            return []

        with patch.object(self.client, '_request', side_effect=fake_request):
            vms = self.client.list_vms()

        self.assertEqual(len(vms), 1)
        vm = vms[0]
        self.assertEqual(vm['uuid'], 'uuid-1')
        self.assertEqual(vm['disks'][0]['storage_container'], 'ds1')
        self.assertEqual(vm['interfaces'][0]['ip_addresses'], ['192.168.1.10/24'])
