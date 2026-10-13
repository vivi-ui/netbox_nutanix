"""
SNMP discovery engine.

Given a :class:`~netbox_snmp.models.SnmpEndpoint`, this module polls the
configured target addresses over SNMP, enumerates each device's interfaces and
IP addresses, follows LLDP/CDP neighbours and reconciles everything against
NetBox's ``dcim.Device`` / ``dcim.Interface`` / ``ipam.IPAddress`` objects.
"""

import ipaddress
import logging
import re
from collections import deque
from dataclasses import dataclass, field

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from dcim.choices import (
    DeviceStatusChoices,
    InterfaceModeChoices,
    InterfaceTypeChoices,
    LinkStatusChoices,
)
from dcim.models import (
    Cable,
    CableTermination,
    Device,
    DeviceRole,
    DeviceType,
    Interface,
    MACAddress,
    Manufacturer,
)
from ipam.choices import IPAddressStatusChoices, PrefixStatusChoices, VLANStatusChoices
from ipam.models import IPAddress, Prefix, VLAN

from .exceptions import SnmpAuthError, SnmpError, SnmpTimeoutError, SyncCancelled
from .models import SnmpDevice, SnmpEndpoint
from .snmp import (
    SnmpClient,
    bytes_to_ip,
    bytes_to_mac,
    decode_text,
    index_suffix,
    mac_from_suffix,
    map_interface_type,
    mask_to_prefix,
    octets_to_ip,
    port_list_to_ports,
    speed_bps,
    speed_kbps,
)
from .snmp import oids

logger = logging.getLogger('netbox.snmp')

VLAN_FROM_NAME = re.compile(r'vlan[^0-9]*(\d+)', re.IGNORECASE)


@dataclass
class NeighborLink:
    """A single LLDP/CDP adjacency observed on a local interface."""

    local_index: int
    remote_sys_name: str = ''
    remote_port_id: str = ''
    remote_port_desc: str = ''
    remote_chassis_id: str = ''
    remote_addresses: set = field(default_factory=set)
    local_interface_name: str = ''
    device: object = None

# Enterprise numbers (iso.org.dod.internet.private.enterprises.<n>) mapped to the
# manufacturer they belong to. Used to derive a NetBox manufacturer from sysObjectID.
VENDOR_BY_ENTERPRISE = {
    9: 'Cisco',
    11: 'Hewlett Packard',
    171: 'D-Link',
    674: 'Dell',
    890: 'ZyXEL',
    14823: 'Aruba',
    14988: 'MikroTik',
    1588: 'Brocade',
    1916: 'Extreme Networks',
    2011: 'Huawei',
    2636: 'Juniper',
    3375: 'F5 Networks',
    41112: 'Ubiquiti',
    4526: 'Netgear',
    4881: 'Ruijie',
    6486: 'Alcatel-Lucent',
    11863: 'TP-Link',
    12356: 'Fortinet',
    25506: 'H3C',
}

ENTERPRISE_PREFIX = [1, 3, 6, 1, 4, 1]

# entPhysicalClass value identifying the chassis entity (used to pick the serial)
ENT_CLASS_CHASSIS = 3


class SyncResult:
    def __init__(self):
        self.created = 0
        self.updated = 0
        self.deleted = 0
        self.cables = 0
        self.errors = 0
        self.discovered = 0
        self.cancelled = False

    def summary(self):
        return (
            f"created={self.created}, updated={self.updated}, "
            f"deleted={self.deleted}, cables={self.cables}, errors={self.errors}"
            f"{', cancelled' if self.cancelled else ''}"
        )


def vendor_name(sys_object_id):
    """Return the manufacturer name implied by a sysObjectID, if known."""
    if not sys_object_id:
        return None
    try:
        parts = [int(part) for part in str(sys_object_id).split('.')]
    except (TypeError, ValueError):
        return None
    if parts[:len(ENTERPRISE_PREFIX)] != ENTERPRISE_PREFIX or len(parts) <= len(ENTERPRISE_PREFIX):
        return None
    return VENDOR_BY_ENTERPRISE.get(parts[len(ENTERPRISE_PREFIX)])


class SnmpSynchronizer:
    def __init__(self, endpoint, log=None, cancel_check=None):
        self.endpoint = endpoint
        self.log = log or logger.info
        self.cancel_check = cancel_check
        self.result = SyncResult()
        self._manufacturer = None
        self._device_types = {}
        self._cable_links = []

    #
    # Orchestration
    #

    def _should_stop(self):
        """Return ``True`` once a cancellation has been requested."""
        if self.cancel_check is None or self.result.cancelled:
            return self.result.cancelled
        try:
            if self.cancel_check():
                self.result.cancelled = True
                self.log("Cancellation requested; stopping discovery.")
        except Exception as e:  # noqa: BLE001 - a failing check must not abort the run
            self.log(f"Cancellation check failed: {e}")
        return self.result.cancelled

    def run(self):
        self.log(f"Starting SNMP sync for endpoint '{self.endpoint}'")

        queue = deque()
        for target in self.endpoint.targets.filter(enabled=True):
            for address in self._expand_target(target.address):
                queue.append((address, 0))

        visited = set()
        managed = set()
        limit = self.endpoint.max_devices or 256

        while queue and len(visited) < limit:
            if self._should_stop():
                break
            address, depth = queue.popleft()
            if address in visited:
                continue
            visited.add(address)

            try:
                addresses, links = self._sync_device(address)
            except SyncCancelled:
                break
            except (SnmpTimeoutError, SnmpAuthError) as e:
                self.result.errors += 1
                self.log(f"ERROR {address}: {e}")
                continue
            except SnmpError as e:
                self.result.errors += 1
                self.log(f"ERROR {address}: {e}")
                continue
            except Exception as e:  # noqa: BLE001 - keep going on unexpected errors
                self.result.errors += 1
                self.log(f"ERROR {address}: {e}")
                continue

            managed.add(address)
            self.result.discovered += 1
            self._cable_links.extend(links)

            if self.endpoint.discover_neighbors and depth < self.endpoint.max_depth:
                for neighbor in addresses:
                    if neighbor not in visited:
                        queue.append((neighbor, depth + 1))

        if not self._should_stop():
            if self.endpoint.create_cables:
                self._sync_cables()

            if self.endpoint.delete_stale:
                self._prune(managed)

        self.log(f"SNMP sync finished for '{self.endpoint}': {self.result.summary()}")
        return self.result

    def _expand_target(self, address):
        """Yield the concrete host addresses for a target (plain IP or CIDR)."""
        address = str(address or '').strip()
        if not address:
            return
        if '/' not in address:
            try:
                yield str(ipaddress.ip_address(address))
            except ValueError:
                return
            return
        try:
            network = ipaddress.ip_network(address, strict=False)
        except ValueError:
            return
        for host in network.hosts():
            yield str(host)

    def _client_for(self, address, retries=None):
        return SnmpClient(
            host=address,
            port=self.endpoint.port,
            version=self.endpoint.snmp_version,
            community=self.endpoint.get_community(),
            security_username=self.endpoint.security_username,
            security_level=self.endpoint.security_level,
            auth_protocol=self.endpoint.auth_protocol,
            auth_key=self.endpoint.get_auth_key(),
            priv_protocol=self.endpoint.priv_protocol,
            priv_key=self.endpoint.get_priv_key(),
            timeout=self.endpoint.timeout,
            retries=self.endpoint.retries if retries is None else retries,
        )

    #
    # Device synchronization
    #

    def _sync_device(self, address):
        client = self._client_for(address)

        # Probe with a single attempt before the full poll: when sweeping a
        # large range, unresponsive hosts would otherwise pay the entire retry
        # budget (timeout x (retries + 1)) before being skipped.
        system = self._client_for(address, retries=0).get_system()
        sys_descr = decode_text(system.get('sys_descr'))
        sys_name = decode_text(system.get('sys_name'))
        if not sys_descr and not sys_name:
            raise SnmpError("Device did not return any system information")

        sys_object_id = system.get('sys_object_id') or ''
        sys_contact = decode_text(system.get('sys_contact'))
        sys_location = decode_text(system.get('sys_location'))
        uptime_ticks = system.get('sys_uptime')
        uptime = int(uptime_ticks) // 100 if uptime_ticks else None

        serial = self._get_serial(client)
        interfaces = self._collect_interfaces(client)
        ip_map = self._collect_ipv4_addresses(client)
        addresses, links = self._collect_neighbors(client)

        bridge_ports = {}
        if self.endpoint.collect_vlans or self.endpoint.collect_fdb:
            bridge_ports = self._collect_bridge_port_map(client)
        vlan_data = self._collect_vlans(client, bridge_ports) if self.endpoint.collect_vlans else []
        fdb_map = self._collect_fdb(client, bridge_ports) if self.endpoint.collect_fdb else {}
        arp_entries = self._collect_arp(client) if self.endpoint.collect_arp else []

        index_to_name = {nic['index']: nic['name'] for nic in interfaces}
        for link in links:
            link.local_interface_name = index_to_name.get(link.local_index, '')

        name = sys_name or address
        device_type = self._resolve_device_type(sys_object_id)

        if self._should_stop():
            raise SyncCancelled()

        with transaction.atomic():
            record = SnmpDevice.objects.filter(
                endpoint=self.endpoint, address=address
            ).first()
            if record is None:
                record = SnmpDevice(endpoint=self.endpoint, address=address)

            device = record.netbox_device
            if device is None and sys_name:
                device = Device.objects.filter(name=sys_name, site=self.endpoint.site).first()

            device_created = device is None
            if device_created:
                device = Device(name=self._unique_device_name(name, address))

            device.device_type = device_type
            device.role = self._get_device_role()
            device.site = self.endpoint.site
            device.status = DeviceStatusChoices.STATUS_ACTIVE
            if self.endpoint.tenant:
                device.tenant = self.endpoint.tenant
            if serial:
                device.serial = serial[:100]
            device.save()

            record.sys_name = name[:255]
            record.sys_object_id = str(sys_object_id)[:255]
            record.sys_descr = sys_descr
            record.sys_location = sys_location[:255]
            record.sys_contact = sys_contact[:255]
            record.serial = (serial or '')[:100]
            record.uptime = uptime
            record.netbox_device = device
            record.last_synced = timezone.now()
            record.save()

            ips, interfaces_by_index = self._sync_interfaces(device, interfaces, ip_map)
            self._set_primary_ips(device, ips, preferred=address)

            vlans_by_vid = {}
            if self.endpoint.collect_vlans:
                vlans_by_vid = self._sync_vlans(device, vlan_data, interfaces_by_index)
            if self.endpoint.infer_prefixes:
                self._sync_prefixes(device, interfaces, ip_map, vlans_by_vid)
            if self.endpoint.collect_arp:
                self._sync_arp(device, arp_entries, fdb_map, interfaces_by_index)

            for link in links:
                link.device = device

        if device_created:
            self.result.created += 1
            self.log(f"Created device '{device}' ({address})")
        else:
            self.result.updated += 1
            self.log(f"Updated device '{device}' ({address})")

        return addresses, links

    def _prune(self, managed):
        for record in SnmpDevice.objects.filter(endpoint=self.endpoint):
            if str(record.address) in managed:
                continue
            device = record.netbox_device
            name = record.sys_name or record.address
            record.delete()
            if device is not None:
                try:
                    device.delete()
                except Exception as e:  # noqa: BLE001
                    self.log(f"Could not delete stale device '{device}': {e}")
            self.result.deleted += 1
            self.log(f"Deleted stale device '{name}'")

    #
    # SNMP collectors
    #

    def _get_serial(self, client):
        try:
            classes = client.walk(oids.ENT_PHYSICAL_CLASS)
            serials = client.walk(oids.ENT_PHYSICAL_SERIAL_NUM)
        except SnmpError:
            return ''

        fallback = ''
        for oid, value in serials.items():
            text = decode_text(value)
            if not text:
                continue
            suffix = index_suffix(oids.ENT_PHYSICAL_SERIAL_NUM, oid)
            if suffix:
                class_value = classes.get(f'{oids.ENT_PHYSICAL_CLASS}.{suffix[0]}')
                if class_value == ENT_CLASS_CHASSIS:
                    return text[:100]
            if not fallback:
                fallback = text
        return fallback[:100]

    def _collect_interfaces(self, client):
        columns = {
            'descr': oids.IF_DESCR,
            'name': oids.IF_NAME,
            'alias': oids.IF_ALIAS,
            'type': oids.IF_TYPE,
            'speed': oids.IF_SPEED,
            'high_speed': oids.IF_HIGH_SPEED,
            'phys': oids.IF_PHYS_ADDRESS,
            'admin': oids.IF_ADMIN_STATUS,
            'mtu': oids.IF_MTU,
        }
        table = {}
        for key, base in columns.items():
            try:
                rows = client.walk(base)
            except SnmpError:
                continue
            for oid, value in rows.items():
                suffix = index_suffix(base, oid)
                if not suffix:
                    continue
                index = suffix[0]
                table.setdefault(index, {})[key] = value

        interfaces = []
        for index, cols in table.items():
            name = decode_text(cols.get('name')) or decode_text(cols.get('descr')) or f'if{index}'
            if_type = cols.get('type') or 0
            speed = speed_bps(cols.get('high_speed'), cols.get('speed'))
            interfaces.append({
                'index': index,
                'name': name[:64],
                'type': map_interface_type(if_type, speed),
                'enabled': cols.get('admin') in (None, 1),
                'description': decode_text(cols.get('alias'))[:200],
                'speed_kbps': speed_kbps(cols.get('high_speed'), cols.get('speed')),
                'mtu': cols.get('mtu') or None,
                'mac': bytes_to_mac(cols.get('phys')),
            })
        return interfaces

    def _collect_ipv4_addresses(self, client):
        """Return ``{ifIndex: {cidr, ...}}`` for the device's IPv4 addresses."""
        try:
            addresses = client.walk(oids.IP_AD_ENT_ADDR)
            if_indexes = client.walk(oids.IP_AD_ENT_IF_INDEX)
            masks = client.walk(oids.IP_AD_ENT_NET_MASK)
        except SnmpError:
            return {}

        result = {}
        for oid, value in addresses.items():
            suffix = index_suffix(oids.IP_AD_ENT_ADDR, oid)
            if not suffix:
                continue
            ip = octets_to_ip(suffix) or bytes_to_ip(value)
            if not ip:
                continue
            index_oid = '.'.join(str(part) for part in suffix)
            if_index = if_indexes.get(f'{oids.IP_AD_ENT_IF_INDEX}.{index_oid}')
            if if_index is None:
                continue
            prefix = mask_to_prefix(masks.get(f'{oids.IP_AD_ENT_NET_MASK}.{index_oid}'))
            cidr = f'{ip}/{prefix if prefix is not None else 32}'
            result.setdefault(int(if_index), set()).add(cidr)
        return result

    def _collect_bridge_port_map(self, client):
        """Return ``{bridge_port: if_index}`` from dot1dBasePortIfIndex."""
        mapping = {}
        for oid, value in self._walk_or_empty(client, oids.DOT1D_BASE_PORT_IF_INDEX).items():
            suffix = index_suffix(oids.DOT1D_BASE_PORT_IF_INDEX, oid)
            if not suffix:
                continue
            try:
                mapping[suffix[0]] = int(value)
            except (TypeError, ValueError):
                continue
        return mapping

    def _collect_vlans(self, client, bridge_ports):
        """
        Return a list of ``{'vid', 'name', 'untagged', 'tagged'}`` entries.

        ``untagged`` and ``tagged`` hold the ifIndexes derived from the
        Q-BRIDGE-MIB static VLAN tables.
        """
        names = self._walk_or_empty(client, oids.DOT1Q_VLAN_STATIC_NAME)
        egress = self._walk_or_empty(client, oids.DOT1Q_VLAN_STATIC_EGRESS)
        untagged = self._walk_or_empty(client, oids.DOT1Q_VLAN_STATIC_UNTAGGED)

        vlans = {}

        def entry(vid):
            return vlans.setdefault(vid, {'vid': vid, 'name': '', 'untagged': set(), 'egress': set()})

        def map_ports(value):
            return {bridge_ports[p] for p in port_list_to_ports(value) if p in bridge_ports}

        for oid, value in names.items():
            suffix = index_suffix(oids.DOT1Q_VLAN_STATIC_NAME, oid)
            if suffix:
                entry(suffix[0])['name'] = decode_text(value)
        for oid, value in untagged.items():
            suffix = index_suffix(oids.DOT1Q_VLAN_STATIC_UNTAGGED, oid)
            if suffix:
                entry(suffix[0])['untagged'] = map_ports(value)
        for oid, value in egress.items():
            suffix = index_suffix(oids.DOT1Q_VLAN_STATIC_EGRESS, oid)
            if suffix:
                entry(suffix[0])['egress'] = map_ports(value)

        result = []
        for vlan in vlans.values():
            vlan['tagged'] = vlan['egress'] - vlan['untagged']
            result.append(vlan)
        return result

    def _collect_fdb(self, client, bridge_ports):
        """Return ``{mac: if_index}`` from the BRIDGE-MIB forwarding table."""
        fdb = {}
        for oid, value in self._walk_or_empty(client, oids.DOT1D_TP_FDB_PORT).items():
            suffix = index_suffix(oids.DOT1D_TP_FDB_PORT, oid)
            if len(suffix) < 6:
                continue
            mac = mac_from_suffix(suffix[:6])
            if not mac:
                continue
            try:
                if_index = bridge_ports.get(int(value))
            except (TypeError, ValueError):
                continue
            if if_index:
                fdb[mac.lower()] = if_index
        return fdb

    def _collect_arp(self, client):
        """Return the device's ARP table as ``{'ip', 'mac', 'if_index'}`` entries."""
        phys = self._walk_or_empty(client, oids.IP_NET_TO_MEDIA_PHYS_ADDRESS)
        entries = []
        for oid, value in phys.items():
            suffix = index_suffix(oids.IP_NET_TO_MEDIA_PHYS_ADDRESS, oid)
            # index: ipNetToMediaIfIndex.<ip octets>
            if len(suffix) < 5:
                continue
            ip = octets_to_ip(suffix[1:])
            if not ip:
                continue
            entries.append({
                'ip': ip,
                'mac': bytes_to_mac(value),
                'if_index': suffix[0],
            })
        return entries

    def _collect_neighbors(self, client):
        """
        Return ``(addresses, links)`` for the device's LLDP/CDP neighbors.

        ``addresses`` is the set of usable neighbour management addresses that
        drives breadth-first discovery; ``links`` carries the per-interface
        adjacency details used later to build cables.
        """
        addresses = set()
        links = []
        links.extend(self._collect_lldp_links(client, addresses))
        links.extend(self._collect_cdp_links(client, addresses))

        usable_links = []
        for link in links:
            link.remote_addresses = {
                ip for ip in link.remote_addresses if self._is_usable_neighbor(ip)
            }
            if link.remote_addresses:
                usable_links.append(link)

        usable_addresses = {ip for ip in addresses if self._is_usable_neighbor(ip)}
        return usable_addresses, usable_links

    def _walk_or_empty(self, client, oid):
        try:
            return client.walk(oid)
        except SnmpError:
            return {}

    def _collect_lldp_links(self, client, addresses):
        entries = {}

        def merge(base, key_name):
            for oid, value in self._walk_or_empty(client, base).items():
                suffix = index_suffix(base, oid)
                # index: timeMark.localPortNum.remIndex
                if len(suffix) < 3:
                    continue
                entries.setdefault(tuple(suffix[:3]), {'local_port': suffix[1]})[key_name] = value

        merge(oids.LLDP_REM_CHASSIS_ID, 'chassis_id')
        merge(oids.LLDP_REM_PORT_ID, 'port_id')
        merge(oids.LLDP_REM_PORT_DESC, 'port_desc')
        merge(oids.LLDP_REM_SYS_NAME, 'sys_name')

        for base in (oids.LLDP_REM_MAN_ADDR_IF_ID, oids.LLDP_REM_MAN_ADDR_IF_SUBTYPE):
            rows = self._walk_or_empty(client, base)
            if not rows:
                continue
            for oid in rows:
                suffix = index_suffix(base, oid)
                # index: timeMark.localPortNum.remIndex.manAddrSubtype.manAddrLen.<address...>
                if len(suffix) < 6:
                    continue
                length = suffix[4]
                if length < 1 or len(suffix) < 5 + length:
                    continue
                ip = octets_to_ip(suffix[5:5 + length])
                if not ip:
                    continue
                entry = entries.setdefault(tuple(suffix[:3]), {'local_port': suffix[1]})
                entry.setdefault('addresses', set()).add(ip)
            break

        links = []
        for entry in entries.values():
            link = self._build_link(
                entry,
                port_id=entry.get('port_id'),
                port_desc=entry.get('port_desc'),
                sys_name=entry.get('sys_name'),
                chassis_id=entry.get('chassis_id'),
            )
            if link is not None:
                addresses |= link.remote_addresses
                links.append(link)
        return links

    def _collect_cdp_links(self, client, addresses):
        entries = {}

        def merge(base, key_name):
            for oid, value in self._walk_or_empty(client, base).items():
                suffix = index_suffix(base, oid)
                # index: cdpCacheIfIndex.cdpCacheDeviceIndex
                if len(suffix) < 2:
                    continue
                entries.setdefault(tuple(suffix[:2]), {'local_port': suffix[0]})[key_name] = value

        merge(oids.CDP_CACHE_DEVICE_ID, 'sys_name')
        merge(oids.CDP_CACHE_DEVICE_PORT, 'port_id')
        merge(oids.CDP_CACHE_ADDRESS, 'address')

        links = []
        for entry in entries.values():
            ip = bytes_to_ip(entry.get('address'))
            link = self._build_link(
                entry,
                port_id=entry.get('port_id'),
                port_desc='',
                sys_name=entry.get('sys_name'),
                chassis_id='',
            )
            if link is None:
                continue
            if ip:
                link.remote_addresses = {ip}
                addresses.add(ip)
            links.append(link)
        return links

    @staticmethod
    def _build_link(entry, port_id, port_desc, sys_name, chassis_id):
        local_index = entry.get('local_port')
        if local_index is None:
            return None
        remote_port_id = decode_text(port_id)
        if not remote_port_id:
            remote_port_id = bytes_to_mac(port_id) or ''
        return NeighborLink(
            local_index=int(local_index),
            remote_sys_name=decode_text(sys_name),
            remote_port_id=remote_port_id,
            remote_port_desc=decode_text(port_desc),
            remote_chassis_id=bytes_to_mac(chassis_id) or decode_text(chassis_id),
            remote_addresses=set(entry.get('addresses') or set()),
        )

    def _is_usable_neighbor(self, address):
        if not address:
            return False
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return False
        if ip.is_loopback or ip.is_unspecified or ip.is_multicast:
            return False
        if ip.is_link_local:
            return False
        return True

    #
    # Cable reconciliation
    #

    def _sync_cables(self):
        if not self._cable_links:
            return
        self.log(f"Connecting {len(self._cable_links)} neighbor link(s)")
        for link in self._cable_links:
            try:
                self._sync_cable(link)
            except Exception as e:  # noqa: BLE001 - a bad link must not abort the run
                self.result.errors += 1
                self.log(f"Could not connect '{link.local_interface_name}': {e}")

    def _sync_cable(self, link):
        if link.device is None or not link.local_interface_name:
            return

        local_interface = Interface.objects.filter(
            device=link.device, name=link.local_interface_name
        ).first()
        if local_interface is None:
            return

        remote_device = self._resolve_remote_device(link)
        if remote_device is None:
            return

        remote_interface = self._resolve_remote_interface(remote_device, link)
        if remote_interface is None or remote_interface.pk == local_interface.pk:
            return

        # A NetBox interface can only terminate a single cable; respect any that
        # already exist so that manually-created cabling is never overwritten.
        if self._is_terminated(local_interface) or self._is_terminated(remote_interface):
            return

        cable = Cable(
            status=LinkStatusChoices.STATUS_CONNECTED,
            a_terminations=[local_interface],
            b_terminations=[remote_interface],
        )
        cable.save()
        self.result.cables += 1
        self.log(f"Connected {local_interface} <-> {remote_interface}")

    def _resolve_remote_device(self, link):
        for address in sorted(link.remote_addresses):
            record = SnmpDevice.objects.filter(
                endpoint=self.endpoint, address=address
            ).first()
            if record is not None and record.netbox_device_id:
                return record.netbox_device
        return None

    def _resolve_remote_interface(self, device, link):
        interfaces = list(Interface.objects.filter(device=device))
        if not interfaces:
            return None

        by_name = {}
        for interface in interfaces:
            by_name.setdefault(self._normalize_interface_name(interface.name), interface)

        for probe in (link.remote_port_id, link.remote_port_desc):
            key = self._normalize_interface_name(probe)
            if key and key in by_name:
                return by_name[key]

        if link.remote_port_id and ':' in link.remote_port_id:
            return Interface.objects.filter(
                device=device,
                primary_mac_address__mac_address__iexact=link.remote_port_id,
            ).first()
        return None

    @staticmethod
    def _normalize_interface_name(name):
        return ''.join(ch for ch in str(name or '').lower() if ch.isalnum())

    @staticmethod
    def _is_terminated(interface):
        content_type = ContentType.objects.get_for_model(interface)
        return CableTermination.objects.filter(
            termination_type=content_type, termination_id=interface.pk
        ).exists()

    #
    # NetBox reconciliation
    #

    def _sync_interfaces(self, device, interfaces, ip_map):
        seen = set()
        ips = []
        by_index = {}
        for nic in interfaces:
            name = nic['name']
            interface, _created = Interface.objects.get_or_create(
                device=device,
                name=name,
                defaults={'type': nic['type'] or InterfaceTypeChoices.TYPE_OTHER},
            )
            interface.type = nic['type'] or interface.type or InterfaceTypeChoices.TYPE_OTHER
            interface.enabled = nic['enabled']
            if nic.get('description'):
                interface.description = nic['description']
            if nic.get('speed_kbps'):
                interface.speed = nic['speed_kbps']
            if nic.get('mtu'):
                interface.mtu = nic['mtu']
            interface.save()

            self._sync_interface_mac(interface, nic.get('mac'))

            for cidr in ip_map.get(nic['index'], set()):
                ip = self._sync_ip_address(cidr, interface)
                if ip is not None:
                    ips.append(ip)
            seen.add(name)
            by_index[nic['index']] = interface

        if self.endpoint.delete_stale:
            device.interfaces.exclude(name__in=seen).delete()
        return ips, by_index

    def _sync_ip_address(self, cidr, interface):
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

    def _sync_interface_mac(self, interface, mac):
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

    @staticmethod
    def _ip_family(ip):
        return 6 if ':' in str(ip.address) else 4

    def _set_primary_ips(self, device, ips, preferred=None):
        preferred_host = None
        if preferred:
            try:
                preferred_host = str(ipaddress.ip_interface(preferred).ip)
            except ValueError:
                preferred_host = None

        updates = {}
        for family, field in ((4, 'primary_ip4'), (6, 'primary_ip6')):
            candidates = [ip for ip in ips if self._ip_family(ip) == family]
            if not candidates:
                continue
            chosen = None
            if preferred_host:
                for candidate in candidates:
                    try:
                        if str(ipaddress.ip_interface(str(candidate.address)).ip) == preferred_host:
                            chosen = candidate
                            break
                    except ValueError:
                        continue
            chosen = chosen or candidates[0]
            if getattr(device, f'{field}_id', None) != chosen.pk:
                updates[field] = chosen

        if updates:
            type(device).objects.filter(pk=device.pk).update(**updates)
            for field, ip in updates.items():
                setattr(device, field, ip)

    #
    # VLAN / prefix / ARP reconciliation
    #

    def _sync_vlans(self, device, vlans, interfaces_by_index):
        by_vid = {}
        for data in vlans:
            vid = int(data['vid'])
            if not 1 <= vid <= 4094:
                continue
            name = (data.get('name') or f'VLAN{vid}')[:64]
            vlan, created = VLAN.objects.get_or_create(
                vid=vid,
                site=self.endpoint.site,
                defaults={'name': name, 'status': VLANStatusChoices.STATUS_ACTIVE},
            )
            if not created and data.get('name') and vlan.name != name:
                vlan.name = name
                vlan.save(update_fields=['name'])
            if self.endpoint.tenant and vlan.tenant_id is None:
                vlan.tenant = self.endpoint.tenant
                vlan.save(update_fields=['tenant'])
            by_vid[vid] = vlan

            for if_index in data['untagged']:
                interface = interfaces_by_index.get(if_index)
                if interface is None:
                    continue
                if (interface.untagged_vlan_id != vlan.pk
                        or interface.mode != InterfaceModeChoices.MODE_ACCESS):
                    interface.untagged_vlan = vlan
                    interface.mode = InterfaceModeChoices.MODE_ACCESS
                    interface.save(update_fields=['untagged_vlan', 'mode'])
            for if_index in data['tagged']:
                interface = interfaces_by_index.get(if_index)
                if interface is None:
                    continue
                interface.tagged_vlans.add(vlan)
                if interface.mode != InterfaceModeChoices.MODE_TAGGED:
                    interface.mode = InterfaceModeChoices.MODE_TAGGED
                    interface.save(update_fields=['mode'])

        return by_vid

    def _sync_prefixes(self, device, interfaces, ip_map, vlans_by_vid):
        for nic in interfaces:
            vid = self._vlan_id_from_name(nic['name'])
            if not vid:
                continue
            for cidr in ip_map.get(nic['index'], set()):
                network = self._network_of(cidr)
                if not network:
                    continue
                vlan = vlans_by_vid.get(vid)
                if vlan is None:
                    vlan, _ = VLAN.objects.get_or_create(
                        vid=vid,
                        site=self.endpoint.site,
                        defaults={'name': f'VLAN{vid}', 'status': VLANStatusChoices.STATUS_ACTIVE},
                    )
                    vlans_by_vid[vid] = vlan
                prefix, _ = Prefix.objects.get_or_create(
                    prefix=network,
                    vrf=None,
                    defaults={
                        'scope': self.endpoint.site,
                        'status': PrefixStatusChoices.STATUS_ACTIVE,
                        'vlan': vlan,
                    },
                )
                updates = []
                if prefix.vlan_id != vlan.pk:
                    prefix.vlan = vlan
                    updates.append('vlan')
                if prefix.scope_id is None:
                    prefix.scope = self.endpoint.site
                    updates.append('scope')
                if updates:
                    prefix.save(update_fields=updates)

    def _sync_arp(self, device, arp_entries, fdb_map, interfaces_by_index):
        limit = self.endpoint.max_arp_entries or 1000
        processed = 0
        content_type = ContentType.objects.get_for_model(Interface)
        for entry in arp_entries:
            if processed >= limit:
                break
            ip = entry['ip']
            if not self._is_usable_neighbor(ip):
                continue
            mac = (entry.get('mac') or '').lower()
            if_index = None
            if mac and self.endpoint.collect_fdb:
                if_index = fdb_map.get(mac)
            if_index = if_index or entry['if_index']
            interface = interfaces_by_index.get(if_index)
            if interface is None:
                continue

            cidr = f'{ip}/32'
            address = IPAddress.objects.filter(
                address=cidr,
                assigned_object_type=content_type,
                assigned_object_id=interface.pk,
            ).first()
            if address is None:
                address = IPAddress.objects.filter(
                    address=cidr, vrf__isnull=True, assigned_object_id__isnull=True
                ).first()
            if address is None:
                address = IPAddress(address=cidr)
            address.status = IPAddressStatusChoices.STATUS_ACTIVE
            if address.assigned_object_id is None:
                address.assigned_object = interface
            if self.endpoint.tenant and address.tenant_id is None:
                address.tenant = self.endpoint.tenant
            if mac and not address.description:
                address.description = f'ARP {mac}'
            address.save()
            processed += 1

    @staticmethod
    def _vlan_id_from_name(name):
        match = VLAN_FROM_NAME.search(str(name or ''))
        return int(match.group(1)) if match else None

    @staticmethod
    def _network_of(cidr):
        try:
            return str(ipaddress.ip_interface(cidr).network)
        except ValueError:
            return None

    #
    # Supporting object helpers
    #

    def _unique_device_name(self, name, address):
        name = (name or address).strip()[:64] or address
        if not Device.objects.filter(name=name, site=self.endpoint.site).exists():
            return name
        candidate = f'{name} ({address})'[:64]
        if not Device.objects.filter(name=candidate, site=self.endpoint.site).exists():
            return candidate
        suffix = 2
        while True:
            candidate = f'{name} ({address})-{suffix}'[:64]
            if not Device.objects.filter(name=candidate, site=self.endpoint.site).exists():
                return candidate
            suffix += 1

    def _get_manufacturer(self, sys_object_id):
        if self._manufacturer is not None:
            return self._manufacturer
        if self.endpoint.manufacturer:
            self._manufacturer = self.endpoint.manufacturer
            return self._manufacturer
        name = vendor_name(sys_object_id) or 'Generic'
        self._manufacturer, _ = Manufacturer.objects.get_or_create(
            name=name,
            defaults={'slug': slugify(name) or 'generic'},
        )
        return self._manufacturer

    def _resolve_device_type(self, sys_object_id):
        if self.endpoint.device_type:
            return self.endpoint.device_type

        manufacturer = self._get_manufacturer(sys_object_id)
        model_name = (str(sys_object_id).strip() or 'SNMP Device')[:100]
        key = (manufacturer.pk, model_name)
        if key in self._device_types:
            return self._device_types[key]

        device_type = DeviceType.objects.filter(
            manufacturer=manufacturer, model=model_name
        ).first()
        if device_type is None:
            base_slug = slugify(f'{manufacturer.name}-{model_name}')[:90] or 'snmp-device'
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
        self._device_types[key] = device_type
        return device_type

    def _get_device_role(self):
        role = self.endpoint.device_role
        if role is None:
            role, _ = DeviceRole.objects.get_or_create(
                name='Network',
                defaults={'slug': 'network', 'color': '2196f3'},
            )
        return role


def run_sync(endpoint, log=None, cancel_check=None):
    """Convenience wrapper used by the background job and management commands."""
    synchronizer = SnmpSynchronizer(endpoint, log=log, cancel_check=cancel_check)
    return synchronizer.run()


def run_sync_for_all(log=None, cancel_check=None):
    """Synchronize every enabled endpoint. Returns a mapping of endpoint to result."""
    results = {}
    for endpoint in SnmpEndpoint.objects.filter(enabled=True):
        try:
            results[endpoint.pk] = run_sync(endpoint, log=log, cancel_check=cancel_check)
        except Exception as e:  # noqa: BLE001
            (log or logger.info)(f"SNMP sync failed for endpoint '{endpoint}': {e}")
    return results
