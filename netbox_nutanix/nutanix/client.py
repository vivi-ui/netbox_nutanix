"""
A minimal, dependency-light client for the Nutanix REST APIs.

Two deployment models are supported:

* ``pc`` Prism Central (REST API v3, ``/api/nutanix/v3``)
* ``pe`` Prism Element (REST API v2.0, ``/PrismGateway/services/rest/v2.0``)

Both deployments authenticate with HTTP Basic credentials and expose lists of
hosts and virtual machines. The returned dictionaries are deliberately
normalized so that the synchronization engine does not need to care about which
deployment produced them.
"""

import logging

import requests

from ..exceptions import NutanixAPIError, NutanixAuthError

logger = logging.getLogger('netbox.nutanix')

# Length of each page requested from the Prism Central v3 API
PAGE_SIZE = 500

# Prism Central v3 list endpoints use a plural collection name in the URL path
# (POST /hosts/list) but a singular entity kind in the request body (kind=host).
V3_KINDS = {
    'hosts': 'host',
    'vms': 'vm',
    'clusters': 'cluster',
    'images': 'image',
}


class NutanixClient:
    def __init__(self, base_url, username, password, verify_ssl=True, timeout=30, deployment='pc'):
        self.base_url = (base_url or '').rstrip('/')
        self.deployment = deployment
        self.timeout = timeout or 30

        if deployment == 'pe':
            self.api_root = f'{self.base_url}/PrismGateway/services/rest/v2.0/'
        else:
            self.api_root = f'{self.base_url}/api/nutanix/v3/'

        if not verify_ssl:
            try:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            except Exception:  # pragma: no cover - defensive
                pass

        self.session = requests.Session()
        self.session.auth = (username, password)
        self.session.verify = bool(verify_ssl)
        self.session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        })

    #
    # Low level HTTP
    #

    def _request(self, method, path, **kwargs):
        url = f"{self.api_root}{path.lstrip('/')}"
        try:
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)
        except requests.exceptions.RequestException as e:
            raise NutanixAPIError(f"Connection to {url} failed: {e}") from e

        if response.status_code in (401, 403):
            raise NutanixAuthError(
                f"Authentication to {url} failed with HTTP {response.status_code}. "
                "Verify the username/password and that the account has API access."
            )
        if response.status_code >= 400:
            snippet = (response.text or '')[:300]
            raise NutanixAPIError(
                f"API request to {url} failed: HTTP {response.status_code} {snippet}"
            )
        if not response.text:
            return {}
        try:
            return response.json()
        except ValueError as e:
            raise NutanixAPIError(f"Invalid JSON response from {url}: {e}") from e

    def _list_v3(self, collection):
        """Iterate over every entity of the given collection using the v3 list endpoint.

        ``collection`` is the plural name used in the URL path (e.g. ``hosts``);
        the request body must carry the matching singular ``kind`` (e.g. ``host``).
        """
        kind = V3_KINDS.get(collection, collection)
        entities = []
        offset = 0
        while True:
            payload = {'kind': kind, 'length': PAGE_SIZE, 'offset': offset}
            data = self._request('POST', f'{collection}/list', json=payload)
            batch = data.get('entities') or []
            entities.extend(batch)

            total = (data.get('metadata') or {}).get('total_matches')
            offset += PAGE_SIZE
            if not batch or (total is not None and offset >= total):
                break
        return entities

    #
    # Public API
    #

    def test_connection(self):
        """Validate connectivity and credentials. Raises NutanixError on failure."""
        if self.deployment == 'pe':
            self._request('GET', 'cluster')
        else:
            self._request('POST', 'clusters/list', json={'kind': 'cluster', 'length': 1, 'offset': 0})
        return True

    def list_hosts(self):
        """Return a normalized list of hosts."""
        if self.deployment == 'pe':
            data = self._request('GET', 'hosts') or {}
            return [self._normalize_pe_host(e) for e in (data.get('entities') or [])]
        return [self._normalize_pc_host(e) for e in self._list_v3('hosts')]

    def list_vms(self):
        """Return a normalized list of virtual machines."""
        if self.deployment == 'pe':
            data = self._request('GET', 'vms') or {}
            return [self._normalize_pe_vm(e) for e in (data.get('entities') or [])]
        return [self._normalize_pc_vm(e) for e in self._list_v3('vms')]

    #
    # Normalization
    #

    @staticmethod
    def _merge_resources(*resource_dicts):
        merged = {}
        for resources in resource_dicts:
            for key, value in (resources or {}).items():
                if value is not None:
                    merged[key] = value
        return merged

    @staticmethod
    def _bytes_to_gib(value):
        try:
            return int(int(value) / (1024 ** 3))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_interfaces(source):
        """Return a normalized list of network interfaces.

        Handles both Prism Central v3 (``nic_list`` with ``ip_endpoint_list``)
        and Prism Element v2.0 (``virtual_nics``/``nics`` with ``ip_addresses``).
        """
        source = source or {}
        nics = source.get('nic_list')
        if nics is None:
            nics = source.get('virtual_nics')
        if nics is None:
            nics = source.get('nics')
        nics = nics or []

        interfaces = []
        for index, nic in enumerate(nics):
            if not isinstance(nic, dict):
                continue

            addresses = []
            for endpoint in (nic.get('ip_endpoint_list') or []):
                if isinstance(endpoint, dict) and endpoint.get('ip'):
                    addresses.append(str(endpoint['ip']))
            for address in (nic.get('ip_addresses') or []):
                if address and str(address) not in addresses:
                    addresses.append(str(address))

            network_ref = nic.get('subnet_reference') or nic.get('network_reference') or {}
            network_name = nic.get('network_name')
            if not network_name and isinstance(network_ref, dict):
                network_name = network_ref.get('name')

            interfaces.append({
                'index': index,
                'name': nic.get('name') or nic.get('nic_name'),
                'mac_address': (nic.get('mac_address') or '').lower() or None,
                'ip_addresses': addresses,
                'enabled': bool(nic.get('is_connected', nic.get('connected', True))),
                'vlan_id': nic.get('vlan_id'),
                'network_name': network_name,
            })
        return interfaces

    @staticmethod
    def _normalize_disks(source):
        """Return a normalized list of virtual disks.

        Handles both Prism Central v3 (``disk_list``) and Prism Element v2.0
        (``vm_disks``) representations.
        """
        source = source or {}
        disks = source.get('disk_list')
        if disks is None:
            disks = source.get('vm_disks')
        disks = disks or []

        normalized = []
        for index, disk in enumerate(disks):
            if not isinstance(disk, dict):
                continue

            vm_disk = disk.get('vm_disk') or {}
            size = disk.get('disk_size_bytes')
            if size is None and disk.get('disk_size_mib') is not None:
                size = int(disk['disk_size_mib']) * 1024 * 1024
            if size is None:
                size = disk.get('disk_size_in_bytes')
            if size is None:
                size = vm_disk.get('disk_size_in_bytes')

            device_properties = disk.get('device_properties') or {}
            address = device_properties.get('disk_address') or disk.get('disk_address') or {}
            storage_config = disk.get('storage_config') or {}
            container = storage_config.get('storage_container_reference') or {}

            device_index = address.get('device_index')
            if device_index is None:
                device_index = disk.get('device_index', index)

            storage_container = None
            if isinstance(container, dict):
                storage_container = container.get('name')
            storage_container = (
                storage_container
                or disk.get('storage_container_uuid')
                or vm_disk.get('storage_container_uuid')
            )

            normalized.append({
                'uuid': disk.get('uuid') or disk.get('disk_uuid'),
                'device_index': device_index,
                'adapter_type': address.get('adapter_type') or disk.get('adapter_type'),
                'size_bytes': int(size) if size is not None else None,
                'storage_container': storage_container,
            })
        return normalized

    def _normalize_pc_host(self, entity):
        metadata = entity.get('metadata') or {}
        spec = entity.get('spec') or {}
        status = entity.get('status') or {}
        resources = self._merge_resources(spec.get('resources'), status.get('resources'))
        controller_vm = resources.get('controller_vm') or {}
        return {
            'uuid': metadata.get('uuid'),
            'name': status.get('name') or spec.get('name') or metadata.get('uuid'),
            'serial': resources.get('serial') or resources.get('serial_number'),
            'model': resources.get('cpu_model') or resources.get('model'),
            'ip_address': (
                resources.get('ip')
                or resources.get('hypervisor_address')
                or controller_vm.get('ip')
            ),
            'cluster_uuid': (status.get('cluster_reference') or {}).get('uuid'),
            'interfaces': self._normalize_interfaces(resources),
        }

    def _normalize_pe_host(self, entity):
        return {
            'uuid': entity.get('uuid'),
            'name': entity.get('name') or entity.get('uuid'),
            'serial': entity.get('serial'),
            'model': entity.get('cpu_model') or entity.get('model'),
            'ip_address': entity.get('ip') or entity.get('hypervisor_address'),
            'cluster_uuid': entity.get('cluster_uuid'),
            'interfaces': self._normalize_interfaces(entity),
        }

    def _normalize_pc_vm(self, entity):
        metadata = entity.get('metadata') or {}
        spec = entity.get('spec') or {}
        status = entity.get('status') or {}
        resources = self._merge_resources(spec.get('resources'), status.get('resources'))

        sockets = resources.get('num_sockets')
        cores = resources.get('num_vcpus_per_socket') or resources.get('num_cores_per_socket')
        try:
            vcpus = int(sockets) * int(cores) if sockets and cores else None
        except (TypeError, ValueError):
            vcpus = None
        if vcpus is None and resources.get('num_vcpus'):
            try:
                vcpus = int(resources['num_vcpus'])
            except (TypeError, ValueError):
                vcpus = None

        disk_bytes = 0
        for disk in (resources.get('disk_list') or []):
            size = disk.get('disk_size_bytes')
            if size is None and disk.get('disk_size_mib') is not None:
                size = int(disk['disk_size_mib']) * 1024 * 1024
            disk_bytes += int(size or 0)

        return {
            'uuid': metadata.get('uuid'),
            'name': spec.get('name') or status.get('name') or metadata.get('uuid'),
            'power_state': (resources.get('power_state') or '').lower(),
            'vcpus': vcpus,
            'memory_mb': resources.get('memory_size_mib'),
            'disk_gb': self._bytes_to_gib(disk_bytes) if disk_bytes else None,
            'host_uuid': (resources.get('host_reference') or {}).get('uuid'),
            'cluster_uuid': (status.get('cluster_reference') or {}).get('uuid'),
            'interfaces': self._normalize_interfaces(resources),
            'disks': self._normalize_disks(resources),
        }

    def _normalize_pe_vm(self, entity):
        power = (entity.get('power_state') or '').lower()
        vcpus = None
        try:
            if entity.get('num_vcpus'):
                vcpus = int(entity['num_vcpus']) * int(entity.get('num_cores_per_vcpu') or 1)
        except (TypeError, ValueError):
            vcpus = None

        disk_bytes = 0
        for disk in (entity.get('vm_disks') or []):
            disk_bytes += int(disk.get('disk_size_in_bytes') or 0)

        return {
            'uuid': entity.get('uuid'),
            'name': entity.get('name') or entity.get('uuid'),
            'power_state': power,
            'vcpus': vcpus,
            'memory_mb': entity.get('memory_mb'),
            'disk_gb': self._bytes_to_gib(disk_bytes) if disk_bytes else None,
            'host_uuid': entity.get('host_uuid'),
            'cluster_uuid': entity.get('cluster_uuid'),
            'ip_addresses': entity.get('ip_addresses') or [],
            'interfaces': self._normalize_interfaces(entity),
            'disks': self._normalize_disks(entity),
        }
