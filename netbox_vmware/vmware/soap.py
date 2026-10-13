"""
A pyVmomi-backed client for the VMware SOAP (vim25) API.

Unlike the vSphere Automation REST API, the SOAP API is exposed by **every**
ESXi host and vCenter Server (``/sdk``), which makes it the reliable choice for
standalone ESXi endpoints that do not serve the REST API. The returned
dictionaries match the shape produced by
:class:`~netbox_vmware.vmware.client.VMwareClient` so the synchronization engine
can consume either client transparently.
"""

import ipaddress
import logging
import ssl
from urllib.parse import urlparse

from pyVim.connect import Disconnect, SmartConnect
from pyVmomi import vim

from ..exceptions import VMwareAPIError, VMwareAuthError

logger = logging.getLogger('netbox.vmware')

# Maps the vim25 ``VirtualMachinePowerState`` enum onto normalized values.
_POWER_MAP = {
    'poweredon': 'on',
    'poweredoff': 'off',
    'suspended': 'suspended',
}

# Maps the concrete controller device classes onto short adapter labels.
_CONTROLLER_CLASSES = (
    (vim.vm.device.VirtualLsiLogicController, 'SCSI'),
    (vim.vm.device.VirtualLsiLogicSASController, 'SCSI'),
    (vim.vm.device.ParaVirtualSCSIController, 'SCSI'),
    (vim.vm.device.VirtualBusLogicController, 'SCSI'),
    (vim.vm.device.VirtualIDEController, 'IDE'),
    (vim.vm.device.VirtualAHCIController, 'SATA'),
    (vim.vm.device.VirtualNVMEController, 'NVMe'),
)

# Controller device classes, used to collect the controller->adapter map.
_CONTROLLER_BASES = (
    vim.vm.device.VirtualSCSIController,
    vim.vm.device.VirtualIDEController,
    vim.vm.device.VirtualAHCIController,
    vim.vm.device.VirtualNVMEController,
)


def _adapter_label(device):
    for cls, label in _CONTROLLER_CLASSES:
        if isinstance(device, cls):
            return label
    return None


class VMwareSoapClient:
    def __init__(self, base_url, username, password, verify_ssl=True, timeout=30, deployment='esxi'):
        parsed = urlparse(base_url if '://' in base_url else f'https://{base_url}')
        self.host = parsed.hostname or base_url
        self.port = parsed.port or 443
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.deployment = deployment
        self.timeout = timeout or 30

        self._si = None
        self._content = None

    #
    # Connection
    #

    def _ssl_context(self):
        if self.verify_ssl:
            return ssl.create_default_context()
        return ssl._create_unverified_context()

    def connect(self):
        if self._si is not None:
            return self._si
        try:
            self._si = SmartConnect(
                host=self.host,
                user=self.username,
                pwd=self.password,
                port=self.port,
                sslContext=self._ssl_context(),
            )
        except vim.fault.InvalidLogin as e:
            raise VMwareAuthError(
                f"Authentication to {self.host}:{self.port} failed: {e.msg or 'invalid credentials'}"
            ) from e
        except Exception as e:  # noqa: BLE001 - normalize every connection failure
            raise VMwareAPIError(
                f"Connection to {self.host}:{self.port} failed: {e}"
            ) from e
        return self._si

    def disconnect(self):
        if self._si is not None:
            try:
                Disconnect(self._si)
            except Exception:  # pragma: no cover - best effort
                pass
            finally:
                self._si = None
                self._content = None

    def test_connection(self):
        self._content = self.connect().RetrieveContent()
        return True

    def _view(self, obj_type):
        if self._content is None:
            self.test_connection()
        container = self._content.viewManager.CreateContainerView(
            self._content.rootFolder, [obj_type], True
        )
        return list(container.view)

    #
    # Public API
    #

    def list_hosts(self):
        return [self._normalize_host(host) for host in self._view(vim.HostSystem)]

    def list_vms(self):
        return [self._normalize_vm(vm) for vm in self._view(vim.VirtualMachine)]

    #
    # Normalization
    #

    @staticmethod
    def _power(value):
        return _POWER_MAP.get(str(value or '').lower(), 'unknown')

    @staticmethod
    def _prefix_from_netmask(netmask):
        try:
            return ipaddress.IPv4Network(f'0.0.0.0/{netmask}').prefixlen
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _host_serial(host):
        try:
            info = host.hardware.systemInfo.otherIdentifyingInfo or []
        except Exception:  # noqa: BLE001 - property may be unset
            info = []
        for item in info:
            key = getattr(getattr(item, 'identifierType', None), 'key', None)
            if key in ('ServiceTag', 'SerialNumberTag', 'EnclosureSerialNumberTag'):
                value = getattr(item, 'identifierValue', None)
                if value:
                    return value
        return ''

    @staticmethod
    def _host_model(host):
        for source in (
            getattr(getattr(host, 'hardware', None), 'systemInfo', None),
            getattr(getattr(host, 'summary', None), 'hardware', None),
        ):
            model = getattr(source, 'model', None)
            if model:
                return model
        return 'VMware ESXi'

    def _normalize_host(self, host):
        interfaces = []
        mgmt_ip = None
        try:
            vnics = host.config.network.vnic or []
        except Exception:  # noqa: BLE001
            vnics = []

        for index, vnic in enumerate(vnics):
            spec = getattr(vnic, 'spec', None)
            ip_config = getattr(spec, 'ip', None)
            address = getattr(ip_config, 'ipAddress', None)
            netmask = getattr(ip_config, 'subnetMask', None)
            mac = getattr(spec, 'mac', None)
            cidr = None
            if address:
                prefix = self._prefix_from_netmask(netmask) if netmask else None
                cidr = f'{address}/{prefix}' if prefix else address
                if mgmt_ip is None:
                    mgmt_ip = address
            interfaces.append({
                'index': index,
                'name': getattr(vnic, 'device', None) or f'vmk{index}',
                'mac_address': mac.lower() if mac else None,
                'ip_addresses': [cidr] if cidr else [],
                'enabled': True,
                'vlan_id': None,
                'network_name': getattr(vnic, 'portgroup', None) or None,
            })

        if mgmt_ip is None:
            mgmt_ip = getattr(getattr(host, 'summary', None), 'managementServerIp', None)

        return {
            'uuid': self._host_uuid(host),
            'name': host.name,
            'serial': self._host_serial(host),
            'model': self._host_model(host),
            'ip_address': mgmt_ip,
            'cluster_uuid': None,
            'interfaces': interfaces,
        }

    @staticmethod
    def _host_uuid(host):
        try:
            return host.hardware.systemInfo.uuid
        except Exception:  # noqa: BLE001
            return str(host._moId)

    @staticmethod
    def _guest_address_map(vm):
        mapping = {}
        for nic in (getattr(vm.guest, 'net', None) or []):
            mac = getattr(nic, 'macAddress', None) or getattr(nic, 'mac', None)
            if not mac:
                continue
            addresses = [str(a) for a in (getattr(nic, 'ipAddress', None) or [])]
            if addresses:
                mapping[mac.lower()] = addresses
        return mapping

    @staticmethod
    def _datastore_name(backing):
        datastore = getattr(backing, 'datastore', None)
        name = getattr(datastore, 'name', None)
        if name:
            return name
        filename = getattr(backing, 'fileName', None)
        if filename and filename.startswith('['):
            end = filename.find(']')
            if end > 1:
                return filename[1:end]
        return None

    @staticmethod
    def _disk_index(disk, fallback):
        label = getattr(getattr(disk, 'deviceInfo', None), 'label', None) or ''
        digits = ''
        for char in reversed(label):
            if char.isdigit():
                digits = char + digits
            elif digits:
                break
        if digits:
            return int(digits) - 1
        return fallback

    def _normalize_disk(self, disk, controllers, index):
        backing = getattr(disk, 'backing', None)
        size_bytes = getattr(disk, 'capacityInBytes', None)
        if size_bytes is None:
            capacity_kb = getattr(disk, 'capacityInKB', None)
            size_bytes = capacity_kb * 1024 if capacity_kb is not None else None

        uuid = getattr(backing, 'uuid', None) or str(getattr(disk, 'key', index))
        return {
            'uuid': uuid,
            'device_index': self._disk_index(disk, index),
            'adapter_type': controllers.get(getattr(disk, 'controllerKey', None)) or 'SCSI',
            'size_bytes': int(size_bytes) if size_bytes is not None else None,
            'storage_container': self._datastore_name(backing),
        }

    def _normalize_ethernet(self, nic, index, guest_addresses):
        mac = getattr(nic, 'macAddress', None)
        connected = True
        connectable = getattr(nic, 'connectable', None)
        if connectable is not None:
            connected = bool(getattr(connectable, 'connected', True))
        backing = getattr(nic, 'backing', None)
        return {
            'index': index,
            'name': None,
            'mac_address': mac.lower() if mac else None,
            'ip_addresses': guest_addresses.get(mac.lower(), []) if mac else [],
            'enabled': connected,
            'vlan_id': None,
            'network_name': getattr(backing, 'deviceName', None) or None,
        }

    def _normalize_vm(self, vm):
        config = getattr(vm, 'config', None)
        hardware = getattr(config, 'hardware', None)
        devices = list(getattr(hardware, 'device', None) or []) if hardware else []

        controllers = {}
        for device in devices:
            if isinstance(device, _CONTROLLER_BASES):
                controllers[getattr(device, 'key', None)] = _adapter_label(device)

        normalized_disks = []
        normalized_nics = []
        guest_addresses = self._guest_address_map(vm)

        for device in devices:
            if isinstance(device, vim.vm.device.VirtualDisk):
                normalized_disks.append(
                    self._normalize_disk(device, controllers, len(normalized_disks))
                )
            elif isinstance(device, vim.vm.device.VirtualEthernetCard):
                normalized_nics.append(
                    self._normalize_ethernet(device, len(normalized_nics), guest_addresses)
                )

        disk_bytes = sum(d['size_bytes'] for d in normalized_disks if d.get('size_bytes'))

        runtime = getattr(vm, 'runtime', None)
        host_ref = getattr(runtime, 'host', None)
        host_uuid = self._host_uuid(host_ref) if host_ref is not None else None

        return {
            'uuid': getattr(config, 'uuid', None) or str(vm._moId),
            'name': vm.name,
            'power_state': self._power(getattr(runtime, 'powerState', None)),
            'vcpus': getattr(hardware, 'numCPU', None) if hardware else None,
            'memory_mb': getattr(hardware, 'memoryMB', None) if hardware else None,
            'disk_gib': disk_bytes // (1024 ** 3) if disk_bytes else None,
            'disk_mb': disk_bytes // (1024 ** 2) if disk_bytes else None,
            'host_uuid': host_uuid,
            'cluster_uuid': None,
            'interfaces': normalized_nics,
            'disks': normalized_disks,
        }
