"""
Synchronization engine.

Given a :class:`~netbox_vmware.models.VMwareEndpoint` endpoint, this module
pulls the list of hosts and virtual machines from the VMware API and reconciles
them against NetBox's ``dcim.Device`` and ``virtualization.VirtualMachine``
objects, recording the mappings in the plugin's own tables.
"""

import logging

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from dcim.choices import InterfaceTypeChoices
from dcim.models import Device, DeviceRole, DeviceType, Interface, MACAddress, Manufacturer
from ipam.choices import IPAddressStatusChoices
from ipam.models import IPAddress
from virtualization.models import VirtualMachine, VMInterface

from .choices import VMwareDeploymentChoices
from .exceptions import VMwareError
from .models import VMwareEndpoint, VMwareDisk, VMwareHost, VMwareVirtualMachine
from .vmware import VMwareClient, VMwareSoapClient

logger = logging.getLogger('netbox.vmware')

# Maps normalized VMware power states onto NetBox VirtualMachine status values
VM_STATUS_MAP = {
    'on': 'active',
    'poweron': 'active',
    'poweredon': 'active',
    'off': 'off',
    'poweroff': 'off',
    'poweredoff': 'off',
    'paused': 'paused',
    'suspended': 'paused',
}


def map_vm_status(power_state):
    return VM_STATUS_MAP.get((power_state or '').lower(), 'off')


class SyncResult:
    def __init__(self):
        self.created = 0
        self.updated = 0
        self.deleted = 0
        self.errors = 0

    def summary(self):
        return (
            f"created={self.created}, updated={self.updated}, "
            f"deleted={self.deleted}, errors={self.errors}"
        )


class VMwareSynchronizer:
    def __init__(self, endpoint, log=None):
        self.endpoint = endpoint
        self.log = log or logger.info
        self.result = SyncResult()
        self._manufacturer = None
        self._device_types = {}

        if endpoint.deployment == VMwareDeploymentChoices.ESXI:
            # Standalone ESXi hosts frequently expose only the SOAP API.
            self.client = VMwareSoapClient(
                base_url=endpoint.base_url,
                username=endpoint.username,
                password=endpoint.get_password(),
                verify_ssl=endpoint.verify_ssl,
                timeout=endpoint.timeout,
                deployment=endpoint.deployment,
            )
        else:
            self.client = VMwareClient(
                base_url=endpoint.base_url,
                username=endpoint.username,
                password=endpoint.get_password(),
                verify_ssl=endpoint.verify_ssl,
                timeout=endpoint.timeout,
                deployment=endpoint.deployment,
            )

    def close(self):
        for method in ('disconnect', 'logout'):
            callback = getattr(self.client, method, None)
            if callable(callback):
                try:
                    callback()
                except Exception:  # noqa: BLE001 - best effort cleanup
                    pass

    #
    # Orchestration
    #

    def run(self, sync_hosts=True, sync_vms=True):
        self.log(f"Starting VMware sync for endpoint '{self.endpoint}'")
        try:
            self.client.test_connection()

            if sync_hosts:
                self.sync_hosts()
            if sync_vms:
                self.sync_vms()
        finally:
            self.close()

        self.log(f"VMware sync finished for '{self.endpoint}': {self.result.summary()}")
        return self.result

    def sync_hosts(self):
        hosts = self.client.list_hosts()
        self.log(f"Retrieved {len(hosts)} host(s) from VMware")
        seen = set()
        for host in hosts:
            try:
                self._sync_host(host)
                seen.add(str(host.get('uuid')))
            except Exception as e:  # noqa: BLE001 - keep syncing remaining hosts
                self.result.errors += 1
                self.log(f"ERROR syncing host '{host.get('name')}': {e}")

        if self.endpoint.delete_stale:
            self._prune_hosts(seen)

    def sync_vms(self):
        vms = self.client.list_vms()
        self.log(f"Retrieved {len(vms)} virtual machine(s) from VMware")
        seen = set()
        for vm in vms:
            try:
                self._sync_vm(vm)
                seen.add(str(vm.get('uuid')))
            except Exception as e:  # noqa: BLE001 - keep syncing remaining VMs
                self.result.errors += 1
                self.log(f"ERROR syncing VM '{vm.get('name')}': {e}")

        if self.endpoint.delete_stale:
            self._prune_vms(seen)

    #
    # Hosts -> Devices
    #

    def _sync_host(self, data):
        uuid = data.get('uuid')
        if not uuid:
            raise VMwareError("Host entity is missing a UUID")

        name = data.get('name') or str(uuid)
        device_type = self._get_device_type(data.get('model'))

        with transaction.atomic():
            record = VMwareHost.objects.filter(uuid=uuid).first()
            if record is None:
                record = VMwareHost(uuid=uuid)

            device = record.netbox_device
            if device is None:
                device = Device.objects.filter(name=name, site=self.endpoint.site).first()

            device_created = device is None
            if device_created:
                device = Device(name=name)

            device.name = name
            device.device_type = device_type
            device.role = self._get_device_role()
            device.site = self.endpoint.site
            device.status = 'active'
            if self.endpoint.tenant:
                device.tenant = self.endpoint.tenant
            if data.get('serial'):
                device.serial = data['serial']
            device.save()

            record.cluster = self.endpoint
            record.name = name
            record.serial = data.get('serial') or ''
            record.ip_address = data.get('ip_address') or None
            record.netbox_device = device
            record.last_synced = timezone.now()
            record.save()

            interfaces = data.get('interfaces') or []
            if not interfaces and data.get('ip_address'):
                # The vSphere Automation API does not expose the physical NICs of
                # a hypervisor host; represent the management address as a single
                # interface so the host IP is still visible on the device.
                interfaces = [{
                    'index': 0,
                    'name': 'mgmt0',
                    'mac_address': None,
                    'ip_addresses': [data['ip_address']],
                    'enabled': True,
                    'network_name': None,
                }]
            ips = self._sync_host_interfaces(device, interfaces)
            self._set_primary_ips(device, ips)

        if device_created:
            self.result.created += 1
            self.log(f"Created device '{device}'")
        else:
            self.result.updated += 1

    def _prune_hosts(self, seen):
        for record in VMwareHost.objects.filter(cluster=self.endpoint):
            if str(record.uuid) in seen:
                continue
            device = record.netbox_device
            record.delete()
            if device is not None:
                try:
                    device.delete()
                except Exception as e:  # noqa: BLE001
                    self.log(f"Could not delete stale device '{device}': {e}")
            self.result.deleted += 1
            self.log(f"Deleted stale host '{record.name}'")

    #
    # VMs -> VirtualMachines
    #

    def _sync_vm(self, data):
        uuid = data.get('uuid')
        if not uuid:
            raise VMwareError("VM entity is missing a UUID")

        name = data.get('name') or str(uuid)
        cluster = self.endpoint.cluster

        with transaction.atomic():
            record = VMwareVirtualMachine.objects.filter(uuid=uuid).first()
            if record is None:
                record = VMwareVirtualMachine(uuid=uuid)

            vm = record.netbox_vm
            if vm is None and cluster is not None:
                vm = VirtualMachine.objects.filter(name=name, cluster=cluster).first()

            vm_created = vm is None
            if vm_created:
                vm = VirtualMachine(name=name)

            vm.name = name
            if cluster is not None:
                vm.cluster = cluster
            if self.endpoint.tenant:
                vm.tenant = self.endpoint.tenant
            if data.get('vcpus'):
                vm.vcpus = data['vcpus']
            if data.get('memory_mb'):
                vm.memory = data['memory_mb']
            if data.get('disk_mb'):
                # NetBox stores the virtual machine disk size in MB.
                vm.disk = data['disk_mb']
            vm.status = map_vm_status(data.get('power_state'))
            vm.save()

            record.cluster = self.endpoint
            record.name = name
            record.power_state = data.get('power_state') or ''
            record.vcpus = data.get('vcpus')
            record.memory_mb = data.get('memory_mb')
            record.disk_gb = data.get('disk_gib')
            record.host_uuid = data.get('host_uuid') or None
            record.netbox_vm = vm
            record.last_synced = timezone.now()
            record.save()

            ips = self._sync_vm_interfaces(vm, data.get('interfaces') or [])
            self._set_primary_ips(vm, ips)
            self._sync_vm_disks(record, data.get('disks') or [])

        if vm_created:
            self.result.created += 1
            self.log(f"Created virtual machine '{vm}'")
        else:
            self.result.updated += 1

    def _prune_vms(self, seen):
        for record in VMwareVirtualMachine.objects.filter(cluster=self.endpoint):
            if str(record.uuid) in seen:
                continue
            vm = record.netbox_vm
            record.delete()
            if vm is not None:
                try:
                    vm.delete()
                except Exception as e:  # noqa: BLE001
                    self.log(f"Could not delete stale virtual machine '{vm}': {e}")
            self.result.deleted += 1
            self.log(f"Deleted stale virtual machine '{record.name}'")

    #
    # Interfaces, IP addresses and disks
    #

    @staticmethod
    def _normalize_cidr(address):
        address = str(address or '').strip()
        if not address:
            return None
        if '/' in address:
            return address
        suffix = '128' if ':' in address else '32'
        return f'{address}/{suffix}'

    @staticmethod
    def _interface_name(nic):
        name = (nic.get('name') or '').strip()
        if name:
            return name[:64]
        return f"eth{nic.get('index', 0)}"

    def _sync_ip_address(self, address, interface):
        cidr = self._normalize_cidr(address)
        if not cidr:
            return

        content_type = ContentType.objects.get_for_model(interface)
        ip = IPAddress.objects.filter(
            address=cidr,
            assigned_object_type=content_type,
            assigned_object_id=interface.pk,
        ).first()
        if ip is None:
            ip = IPAddress.objects.filter(
                address=cidr,
                vrf__isnull=True,
                assigned_object_id__isnull=True,
            ).first()
        if ip is None:
            ip = IPAddress(address=cidr)

        ip.status = IPAddressStatusChoices.STATUS_ACTIVE
        if self.endpoint.tenant:
            ip.tenant = self.endpoint.tenant
        ip.assigned_object = interface
        ip.save()
        return ip

    @staticmethod
    def _ip_family(ip):
        # In-memory IPAddress instances hold ``address`` as a string until reloaded
        # from the database, so derive the family from the textual address.
        return 6 if ':' in str(ip.address) else 4

    @staticmethod
    def _set_primary_ips(obj, ips):
        """Assign the first IPv4/IPv6 address as the object's primary address.

        Setting ``primary_ip4``/``primary_ip6`` makes the address visible on the
        natively rendered device/virtual machine pages and lists.
        """
        updates = {}
        for family, field in ((4, 'primary_ip4'), (6, 'primary_ip6')):
            ip = next(
                (candidate for candidate in ips if VMwareSynchronizer._ip_family(candidate) == family),
                None,
            )
            if ip is not None and getattr(obj, f'{field}_id', None) != ip.pk:
                updates[field] = ip
        if updates:
            type(obj).objects.filter(pk=obj.pk).update(**updates)
            for field, ip in updates.items():
                setattr(obj, field, ip)

    def _sync_interface_mac(self, interface, mac):
        """Attach a MAC address to an interface.

        NetBox 4.4 models MAC addresses as standalone ``dcim.MACAddress``
        objects linked to an interface via a generic foreign key; the interface's
        ``mac_address`` attribute is a read-only convenience property.
        """
        mac = (mac or '').strip().lower()
        if not mac:
            return

        content_type = ContentType.objects.get_for_model(interface)
        mac_obj = MACAddress.objects.filter(
            mac_address=mac,
            assigned_object_type=content_type,
            assigned_object_id=interface.pk,
        ).first()
        if mac_obj is None:
            mac_obj = MACAddress(mac_address=mac, assigned_object=interface)
            mac_obj.save()

        if interface.primary_mac_address_id != mac_obj.pk:
            interface.primary_mac_address = mac_obj
            interface.save(update_fields=['primary_mac_address'])

    def _sync_host_interfaces(self, device, interfaces):
        ips = []
        for nic in interfaces:
            interface, created = Interface.objects.get_or_create(
                device=device,
                name=self._interface_name(nic),
                defaults={'type': InterfaceTypeChoices.TYPE_OTHER},
            )
            if not created and not interface.type:
                interface.type = InterfaceTypeChoices.TYPE_OTHER

            interface.enabled = bool(nic.get('enabled', True))
            if nic.get('network_name'):
                interface.description = nic['network_name']
            interface.save()

            self._sync_interface_mac(interface, nic.get('mac_address'))

            for address in nic.get('ip_addresses') or []:
                ip = self._sync_ip_address(address, interface)
                if ip is not None:
                    ips.append(ip)
        return ips

    def _sync_vm_interfaces(self, vm, interfaces):
        ips = []
        for nic in interfaces:
            interface, created = VMInterface.objects.get_or_create(
                virtual_machine=vm,
                name=self._interface_name(nic),
            )

            interface.enabled = bool(nic.get('enabled', True))
            if nic.get('network_name'):
                interface.description = nic['network_name']
            interface.save()

            self._sync_interface_mac(interface, nic.get('mac_address'))

            for address in nic.get('ip_addresses') or []:
                ip = self._sync_ip_address(address, interface)
                if ip is not None:
                    ips.append(ip)
        return ips

    def _sync_vm_disks(self, record, disks):
        seen = set()
        for disk in disks:
            disk_uuid = disk.get('uuid')
            device_index = disk.get('device_index')

            obj = None
            if disk_uuid:
                obj = record.disks.filter(uuid=disk_uuid).first()
            elif device_index is not None:
                # Fall back to the device index only for entries without a UUID so
                # that same-index devices (e.g. disks and CD-ROMs) never collide.
                obj = record.disks.filter(uuid__isnull=True, device_index=device_index).first()
            if obj is None:
                obj = VMwareDisk(virtual_machine=record)

            obj.uuid = disk_uuid or None
            obj.device_index = device_index
            obj.adapter_type = (disk.get('adapter_type') or '')[:50]
            obj.size_bytes = disk.get('size_bytes')
            obj.storage_container = (disk.get('storage_container') or '')[:255]
            obj.save()
            seen.add(obj.pk)

        if self.endpoint.delete_stale:
            record.disks.exclude(pk__in=seen).delete()

    #
    # Supporting object helpers
    #

    def _get_manufacturer(self):
        if self._manufacturer is None:
            self._manufacturer = self.endpoint.manufacturer
            if self._manufacturer is None:
                self._manufacturer, _ = Manufacturer.objects.get_or_create(
                    name='VMware',
                    defaults={'slug': 'vmware'},
                )
        return self._manufacturer

    def _get_device_role(self):
        role = self.endpoint.device_role
        if role is None:
            role, _ = DeviceRole.objects.get_or_create(
                name='VMware Node',
                defaults={'slug': 'vmware-node', 'color': '9e9e9e'},
            )
        return role

    def _get_device_type(self, model_name):
        model_name = (model_name or 'VMware Node').strip()[:100] or 'VMware Node'
        if model_name in self._device_types:
            return self._device_types[model_name]

        manufacturer = self._get_manufacturer()
        device_type = DeviceType.objects.filter(manufacturer=manufacturer, model=model_name).first()
        if device_type is None:
            base_slug = slugify(model_name)[:90] or 'vmware-node'
            slug = base_slug
            counter = 1
            while DeviceType.objects.filter(slug=slug).exists():
                counter += 1
                slug = f'{base_slug[:85]}-{counter}'
            device_type = DeviceType.objects.create(
                manufacturer=manufacturer,
                model=model_name,
                slug=slug,
            )
        self._device_types[model_name] = device_type
        return device_type


def run_sync(endpoint, log=None, sync_hosts=True, sync_vms=True):
    """Convenience wrapper used by the background job and management commands."""
    synchronizer = VMwareSynchronizer(endpoint, log=log)
    return synchronizer.run(sync_hosts=sync_hosts, sync_vms=sync_vms)


def run_sync_for_all(log=None, sync_hosts=True, sync_vms=True):
    """Synchronize every enabled endpoint. Returns a mapping of endpoint to result."""
    results = {}
    for endpoint in VMwareEndpoint.objects.filter(enabled=True):
        try:
            results[endpoint.pk] = run_sync(
                endpoint, log=log, sync_hosts=sync_hosts, sync_vms=sync_vms
            )
        except Exception as e:  # noqa: BLE001
            (log or logger.info)(f"VMware sync failed for endpoint '{endpoint}': {e}")
    return results
