from types import SimpleNamespace

from django.test import SimpleTestCase
from pyVmomi import vim

from netbox_vmware.vmware.soap import VMwareSoapClient


def _description(label):
    info = vim.Description()
    info.label = label
    return info


def _controller(cls, key, label='SCSI controller 0'):
    controller = cls()
    controller.key = key
    controller.deviceInfo = _description(label)
    return controller


def _disk(key, controller_key, size_bytes, filename, uuid=None, label='Hard disk 1'):
    disk = vim.vm.device.VirtualDisk()
    disk.key = key
    disk.controllerKey = controller_key
    disk.capacityInBytes = size_bytes
    disk.deviceInfo = _description(label)
    backing = vim.vm.device.VirtualDisk.FlatVer2BackingInfo()
    backing.fileName = filename
    if uuid:
        backing.uuid = uuid
    disk.backing = backing
    return disk


def _nic(key, mac, device_name='VM Network', connected=True, label='Network adapter 1'):
    nic = vim.vm.device.VirtualE1000()
    nic.key = key
    nic.macAddress = mac
    nic.deviceInfo = _description(label)
    nic.connectable = vim.vm.device.VirtualDevice.ConnectInfo()
    nic.connectable.connected = connected
    nic.backing = vim.vm.device.VirtualEthernetCard.NetworkBackingInfo()
    nic.backing.deviceName = device_name
    return nic


def _vm(name='web-01', uuid='vm-uuid', power='poweredOn', devices=None, guest_nets=None,
        host_uuid=None):
    vm = SimpleNamespace(name=name, _moId='vm-1')
    vm.config = SimpleNamespace(
        uuid=uuid,
        hardware=SimpleNamespace(numCPU=2, memoryMB=2048, device=devices or []),
    )
    vm.runtime = SimpleNamespace(powerState=power, host=None)
    if host_uuid:
        vm.runtime.host = SimpleNamespace(
            hardware=SimpleNamespace(systemInfo=SimpleNamespace(uuid=host_uuid))
        )
    vm.guest = SimpleNamespace(net=guest_nets or [])
    return vm


def _guest_nic(mac, addresses):
    info = SimpleNamespace(macAddress=mac, ipAddress=addresses)
    return info


def _host(name='esxi1', uuid='host-uuid', model='ProLiant DL380p Gen8',
          serial='SGH2174KRX', management_ip='10.0.0.5'):
    host = SimpleNamespace(name=name, _moId='host-1')
    ident = SimpleNamespace(
        identifierType=SimpleNamespace(key='ServiceTag'),
        identifierValue=serial,
    )
    host.hardware = SimpleNamespace(
        systemInfo=SimpleNamespace(
            uuid=uuid, model=model, otherIdentifyingInfo=[ident]
        )
    )
    host.summary = SimpleNamespace(managementServerIp=management_ip)
    vnic = SimpleNamespace(
        device='vmk0',
        portgroup='Management Network',
        spec=SimpleNamespace(
            mac='2C:76:8A:53:7D:6B',
            ip=SimpleNamespace(ipAddress=management_ip, subnetMask='255.255.255.0'),
        ),
    )
    host.config = SimpleNamespace(network=SimpleNamespace(vnic=[vnic]))
    return host


class SoapHelperTestCase(SimpleTestCase):
    def test_power_normalization(self):
        self.assertEqual(VMwareSoapClient._power('poweredOn'), 'on')
        self.assertEqual(VMwareSoapClient._power('poweredOff'), 'off')
        self.assertEqual(VMwareSoapClient._power('suspended'), 'suspended')
        self.assertEqual(VMwareSoapClient._power('mystery'), 'unknown')

    def test_prefix_from_netmask(self):
        self.assertEqual(VMwareSoapClient._prefix_from_netmask('255.255.255.0'), 24)
        self.assertEqual(VMwareSoapClient._prefix_from_netmask('255.255.0.0'), 16)
        self.assertIsNone(VMwareSoapClient._prefix_from_netmask('not-a-mask'))

    def test_disk_index_from_label(self):
        disk = _disk(2000, 1000, 1024, '[ds] vm/disk.vmdk', label='Hard disk 3')
        self.assertEqual(VMwareSoapClient._disk_index(disk, fallback=9), 2)

    def test_datastore_name_from_backing(self):
        backing = vim.vm.device.VirtualDisk.FlatVer2BackingInfo()
        backing.fileName = '[datastore1] vm/disk.vmdk'
        self.assertEqual(VMwareSoapClient._datastore_name(backing), 'datastore1')


class SoapVmNormalizationTestCase(SimpleTestCase):
    def setUp(self):
        self.client = VMwareSoapClient('https://esxi.example.com', 'root', 'secret')

    def test_normalize_vm(self):
        devices = [
            _controller(vim.vm.device.ParaVirtualSCSIController, 1000),
            _disk(2000, 1000, 20 * 1024 ** 3, '[datastore1] web-01/web-01.vmdk',
                  uuid='disk-uuid-1'),
            _nic(4000, '00:0C:29:15:05:FF'),
        ]
        guest_nets = [_guest_nic('00:0c:29:15:05:ff', ['10.0.0.10', 'fe80::1'])]
        vm = _vm(devices=devices, guest_nets=guest_nets, host_uuid='host-uuid-1')

        data = self.client._normalize_vm(vm)
        self.assertEqual(data['uuid'], 'vm-uuid')
        self.assertEqual(data['name'], 'web-01')
        self.assertEqual(data['power_state'], 'on')
        self.assertEqual(data['vcpus'], 2)
        self.assertEqual(data['memory_mb'], 2048)
        self.assertEqual(data['disk_gib'], 20)
        self.assertEqual(data['disk_mb'], 20 * 1024)
        self.assertEqual(data['host_uuid'], 'host-uuid-1')

        self.assertEqual(len(data['disks']), 1)
        self.assertEqual(data['disks'][0]['uuid'], 'disk-uuid-1')
        self.assertEqual(data['disks'][0]['device_index'], 0)
        self.assertEqual(data['disks'][0]['adapter_type'], 'SCSI')
        self.assertEqual(data['disks'][0]['size_bytes'], 20 * 1024 ** 3)
        self.assertEqual(data['disks'][0]['storage_container'], 'datastore1')

        self.assertEqual(len(data['interfaces']), 1)
        self.assertEqual(data['interfaces'][0]['mac_address'], '00:0c:29:15:05:ff')
        self.assertEqual(data['interfaces'][0]['ip_addresses'], ['10.0.0.10', 'fe80::1'])
        self.assertEqual(data['interfaces'][0]['network_name'], 'VM Network')
        self.assertTrue(data['interfaces'][0]['enabled'])

    def test_normalize_vm_without_config(self):
        vm = SimpleNamespace(
            name='orphan',
            _moId='vm-orphan',
            config=None,
            runtime=SimpleNamespace(powerState='poweredOff', host=None),
            guest=SimpleNamespace(net=[]),
        )

        data = self.client._normalize_vm(vm)
        self.assertEqual(data['name'], 'orphan')
        self.assertEqual(data['power_state'], 'off')
        self.assertIsNone(data['vcpus'])
        self.assertEqual(data['disks'], [])
        self.assertEqual(data['interfaces'], [])


class SoapHostNormalizationTestCase(SimpleTestCase):
    def setUp(self):
        self.client = VMwareSoapClient('https://esxi.example.com', 'root', 'secret')

    def test_normalize_host(self):
        data = self.client._normalize_host(_host())
        self.assertEqual(data['uuid'], 'host-uuid')
        self.assertEqual(data['name'], 'esxi1')
        self.assertEqual(data['serial'], 'SGH2174KRX')
        self.assertEqual(data['model'], 'ProLiant DL380p Gen8')
        self.assertEqual(data['ip_address'], '10.0.0.5')
        self.assertEqual(len(data['interfaces']), 1)
        self.assertEqual(data['interfaces'][0]['name'], 'vmk0')
        self.assertEqual(data['interfaces'][0]['mac_address'], '2c:76:8a:53:7d:6b')
        self.assertEqual(data['interfaces'][0]['ip_addresses'], ['10.0.0.5/24'])
        self.assertEqual(data['interfaces'][0]['network_name'], 'Management Network')
