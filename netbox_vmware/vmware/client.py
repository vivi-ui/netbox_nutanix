"""
A minimal, dependency-light client for the VMware vSphere Automation REST API.

The vSphere Automation API lives under ``/api`` and is exposed by both vCenter
Server and (a subset of it) by standalone ESXi hosts:

* ``vcenter`` - a vCenter Server, exposing the full ``/api`` tree
* ``esxi``    - a standalone ESXi host, exposing a subset of ``/api``

Both deployments authenticate by creating a session (``POST /api/session``) and
then passing the returned session id in the ``vmware-api-session-id`` header.
The returned dictionaries are normalized so that the synchronization engine does
not need to care about which deployment produced them.
"""

import ipaddress
import logging
import re
from urllib.parse import urlparse

import requests

from ..exceptions import VMwareAPIError, VMwareAuthError

logger = logging.getLogger('netbox.vmware')

# Maps VMware power states (``POWERED_ON`` etc.) onto our normalized values.
_POWER_MAP = {
    'powered_on': 'on',
    'poweredon': 'on',
    'on': 'on',
    'powered_off': 'off',
    'poweredoff': 'off',
    'off': 'off',
    'suspended': 'suspended',
    'suspend': 'suspended',
    'paused': 'suspended',
}

# Matches a datastore name inside a vmdk path such as "[datastore1] vm/disk.vmdk".
_DATASTORE_RE = re.compile(r'\[([^\]]+)\]')

# Matches the trailing index of a label such as "Hard disk 1" or "Network adapter 2".
_LABEL_INDEX_RE = re.compile(r'(\d+)\s*$')


def _looks_like_ip(value):
    try:
        ipaddress.ip_address(value)
        return True
    except (TypeError, ValueError):
        return False


class VMwareClient:
    def __init__(self, base_url, username, password, verify_ssl=True, timeout=30, deployment='vcenter'):
        self.base_url = (base_url or '').rstrip('/')
        self.username = username
        self.password = password
        self.deployment = deployment
        self.timeout = timeout or 30
        self.api_root = f'{self.base_url}/api'
        self._session_id = None

        if not verify_ssl:
            try:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            except Exception:  # pragma: no cover - defensive
                pass

        self.session = requests.Session()
        self.session.verify = bool(verify_ssl)
        self.session.headers.update({'Accept': 'application/json'})

    #
    # Low level HTTP
    #

    def login(self):
        """Create a vSphere Automation session and store its id for later calls."""
        url = f'{self.api_root}/session'
        try:
            response = self.session.post(
                url, auth=(self.username, self.password), timeout=self.timeout
            )
        except requests.exceptions.RequestException as e:
            raise VMwareAPIError(f"Connection to {url} failed: {e}") from e

        if response.status_code in (401, 403):
            raise VMwareAuthError(
                f"Authentication to {url} failed with HTTP {response.status_code}. "
                "Verify the username/password and that the account has API access."
            )
        if response.status_code >= 400:
            snippet = (response.text or '')[:300]
            raise VMwareAPIError(
                f"API request to {url} failed: HTTP {response.status_code} {snippet}"
            )

        try:
            session_id = response.json()
        except ValueError:
            session_id = (response.text or '').strip().strip('"')
        if not session_id:
            raise VMwareAuthError("The endpoint did not return a session id.")

        self._session_id = session_id
        self.session.headers['vmware-api-session-id'] = session_id
        return session_id

    def logout(self):
        if not self._session_id:
            return
        try:
            self.session.delete(f'{self.api_root}/session', timeout=self.timeout)
        except requests.exceptions.RequestException:  # pragma: no cover - best effort
            pass
        finally:
            self._session_id = None
            self.session.headers.pop('vmware-api-session-id', None)

    def _request(self, method, path, **kwargs):
        if not self._session_id:
            self.login()

        url = f"{self.api_root}/{path.lstrip('/')}"
        try:
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)
        except requests.exceptions.RequestException as e:
            raise VMwareAPIError(f"Connection to {url} failed: {e}") from e

        if response.status_code in (401, 403):
            # The session may have expired; re-authenticate once and retry.
            self._session_id = None
            self.session.headers.pop('vmware-api-session-id', None)
            self.login()
            try:
                response = self.session.request(method, url, timeout=self.timeout, **kwargs)
            except requests.exceptions.RequestException as e:
                raise VMwareAPIError(f"Connection to {url} failed: {e}") from e

        if response.status_code >= 400:
            snippet = (response.text or '')[:300]
            raise VMwareAPIError(
                f"API request to {url} failed: HTTP {response.status_code} {snippet}"
            )
        if not response.text:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    #
    # Public API
    #

    def test_connection(self):
        """Validate connectivity and credentials. Raises VMwareError on failure."""
        self.login()
        return True

    def list_hosts(self):
        """Return a normalized list of hosts."""
        try:
            entries = self._request('GET', 'vcenter/host') or []
        except VMwareAPIError:
            entries = []

        hosts = [self._normalize_host(entry) for entry in entries if isinstance(entry, dict)]
        if not hosts and self.deployment == 'esxi':
            hosts.append(self._normalize_standalone_host())
        return hosts

    def list_vms(self):
        """Return a normalized list of virtual machines."""
        entries = self._request('GET', 'vcenter/vm') or []
        vms = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            vm_id = entry.get('vm')
            if not vm_id:
                continue
            detail = self._request('GET', f'vcenter/vm/{vm_id}') or {}
            disks = self._safe_list(f'vcenter/vm/{vm_id}/hardware/disk')
            ethernet = self._safe_list(f'vcenter/vm/{vm_id}/hardware/ethernet')
            guest = self._safe_list(f'vcenter/vm/{vm_id}/guest/networking/interfaces')
            vms.append(self._normalize_vm(entry, detail, disks, ethernet, guest))
        return vms

    def _safe_list(self, path):
        try:
            data = self._request('GET', path)
        except VMwareAPIError:
            return []
        return data if isinstance(data, list) else []

    #
    # Normalization
    #

    @staticmethod
    def _normalize_power(value):
        return _POWER_MAP.get((value or '').lower(), 'unknown')

    @staticmethod
    def _datastore_from_backing(backing):
        if not isinstance(backing, dict):
            return None
        vmdk = backing.get('vmdk_file')
        if vmdk:
            match = _DATASTORE_RE.search(vmdk)
            if match:
                return match.group(1)
        return None

    @classmethod
    def _normalize_disk(cls, entry, index):
        """Normalize a single virtual disk from ``/hardware/disk``."""
        entry = entry or {}
        label = entry.get('label') or ''
        match = _LABEL_INDEX_RE.search(label)
        device_index = int(match.group(1)) - 1 if match else index

        size = entry.get('capacity')
        return {
            'uuid': str(entry.get('disk')) if entry.get('disk') is not None else None,
            'device_index': device_index,
            'adapter_type': (entry.get('type') or '').upper() or None,
            'size_bytes': int(size) if size is not None else None,
            'storage_container': cls._datastore_from_backing(entry.get('backing')),
        }

    @classmethod
    def _normalize_ethernet(cls, entry, index, guest_addresses):
        """Normalize a single NIC from ``/hardware/ethernet``."""
        entry = entry or {}
        backing = entry.get('backing') or {}
        mac = (entry.get('mac_address') or '').lower() or None

        addresses = []
        if mac and mac in guest_addresses:
            addresses = guest_addresses[mac]
        elif entry.get('mac_address') and entry['mac_address'].lower() in guest_addresses:
            addresses = guest_addresses[entry['mac_address'].lower()]

        network_name = None
        if isinstance(backing, dict):
            network_name = backing.get('network_name') or backing.get('network')

        return {
            'index': index,
            'name': None,
            'mac_address': mac,
            'ip_addresses': addresses,
            'enabled': (entry.get('state') or 'CONNECTED').upper() == 'CONNECTED',
            'vlan_id': None,
            'network_name': network_name,
        }

    @staticmethod
    def _guest_address_map(guest_interfaces):
        """Map MAC addresses to ``ip/prefix`` strings using guest networking data."""
        mapping = {}
        for nic in guest_interfaces or []:
            if not isinstance(nic, dict):
                continue
            mac = (nic.get('mac_address') or '').lower()
            if not mac:
                continue
            ip_info = nic.get('ip') or {}
            prefix = ip_info.get('prefix_length')
            addresses = []
            for address in ip_info.get('ip_addresses') or []:
                address = str(address)
                if prefix and '/' not in address:
                    address = f'{address}/{prefix}'
                addresses.append(address)
            if addresses:
                mapping[mac] = addresses
        return mapping

    def _normalize_vm(self, summary, detail, disks, ethernet, guest_interfaces):
        summary = summary or {}
        detail = detail or {}
        identity = detail.get('identity') or {}

        vm_id = summary.get('vm') or detail.get('vm')
        uuid = identity.get('instance_uuid') or summary.get('identity', {}).get('instance_uuid') or vm_id
        name = detail.get('name') or summary.get('name') or str(vm_id)

        cpu = detail.get('cpu') or {}
        memory = detail.get('memory') or {}
        vcpus = cpu.get('count') or summary.get('cpu_count')
        if vcpus is not None:
            try:
                vcpus = int(vcpus)
            except (TypeError, ValueError):
                vcpus = None

        memory_mb = memory.get('size_MiB') or summary.get('memory_size_MiB')
        if memory_mb is not None:
            try:
                memory_mb = int(memory_mb)
            except (TypeError, ValueError):
                memory_mb = None

        normalized_disks = [
            self._normalize_disk(disk, index) for index, disk in enumerate(disks or [])
        ]
        disk_bytes = sum(d['size_bytes'] for d in normalized_disks if d.get('size_bytes'))

        guest_addresses = self._guest_address_map(guest_interfaces)
        normalized_nics = [
            self._normalize_ethernet(nic, index, guest_addresses)
            for index, nic in enumerate(ethernet or [])
        ]

        return {
            'uuid': uuid,
            'name': name,
            'power_state': self._normalize_power(detail.get('power_state') or summary.get('power_state')),
            'vcpus': vcpus,
            'memory_mb': memory_mb,
            'disk_gib': self._bytes_to_gib(disk_bytes) if disk_bytes else None,
            'disk_mb': disk_bytes // (1024 ** 2) if disk_bytes else None,
            'host_uuid': None,
            'cluster_uuid': None,
            'interfaces': normalized_nics,
            'disks': normalized_disks,
        }

    @staticmethod
    def _bytes_to_gib(value):
        try:
            return int(int(value) / (1024 ** 3))
        except (TypeError, ValueError):
            return None

    def _normalize_host(self, entry):
        entry = entry or {}
        host_id = entry.get('host')
        name = entry.get('name') or host_id
        ip_address = name if _looks_like_ip(name) else None
        return {
            'uuid': host_id,
            'name': name,
            'serial': '',
            'model': 'VMware ESXi',
            'ip_address': ip_address,
            'cluster_uuid': None,
            'interfaces': [],
        }

    def _normalize_standalone_host(self):
        """Describe the standalone ESXi host that the endpoint points at."""
        hostname = urlparse(self.base_url).hostname or self.base_url
        ip_address = hostname if _looks_like_ip(hostname) else None
        return {
            'uuid': hostname,
            'name': hostname,
            'serial': '',
            'model': 'VMware ESXi',
            'ip_address': ip_address,
            'cluster_uuid': None,
            'interfaces': [],
        }
