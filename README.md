# netbox-vmware

A NetBox plugin that synchronizes **VMware** infrastructure into NetBox:

* VMware **hosts** (hypervisor nodes) are reconciled as `dcim.Device` objects,
  including their network interfaces (`dcim.Interface`), MAC addresses
  (`dcim.MACAddress`) and assigned IP addresses (`ipam.IPAddress`).
* VMware **virtual machines** are reconciled as `virtualization.VirtualMachine`
  objects, including their network interfaces (`virtualization.VMInterface`),
  assigned IP addresses and per-disk records (`VMwareDisk`).

The plugin talks to VMware over the API best suited to each endpoint type:

* **vCenter Server** is queried through the **vSphere Automation REST API**
  (`/api`).
* **Standalone ESXi** hosts are queried through the **SOAP (vim25) API**
  (`/sdk`), which is available on every ESXi host even when the REST API is not.

Discovered objects are stored in the plugin's own tables so that mappings can be
tracked over time, and synchronization runs as a background job.

## Requirements

| Component | Version |
|-----------|---------|
| NetBox    | 4.4 – 4.6 |
| Python    | 3.10+ |

## Installation

```bash
# From the plugin root directory
pip install .
```

Enable the plugin in your NetBox `configuration.py`:

```python
PLUGINS = [
    'netbox_vmware',
]
```

Optional plugin settings:

```python
PLUGINS_CONFIG = {
    'netbox_vmware': {
        # Minutes between periodic syncs. 0 (the default) disables the recurring job.
        'sync_interval': 0,
        # Default request timeout (seconds) for new endpoints.
        'request_timeout': 30,
        # Verify TLS certificates by default.
        'verify_ssl': True,
    },
}
```

Then run migrations and restart NetBox:

```bash
python manage.py migrate netbox_vmware
sudo systemctl restart netbox netbox-rq
```

## Usage

1. Navigate to **VMware > Endpoints** and add an endpoint with the vCenter/ESXi
   URL, credentials and synchronization defaults (site, device role,
   virtualization cluster).
2. Open the endpoint and click **Sync now**. A background job is enqueued; open
   the entry under the **Jobs** tab to watch progress.
3. Discovered hosts appear under **VMware > Hosts** and virtual machines under
   **VMware > Virtual Machines**. Each record links to the corresponding
   NetBox device or virtual machine. Virtual machine disks are listed under
   **VMware > Disks** and beneath each virtual machine.

### Endpoint options

| Field | Description |
|-------|-------------|
| Deployment | `vCenter Server` (vSphere Automation REST) or `Standalone ESXi` (SOAP/vim25). |
| Base URL | e.g. `https://vcenter.example.com` or `https://esxi.example.com` |
| Verify SSL | Disable for self-signed certificates (not recommended). |
| Site | Site assigned to synchronized devices. |
| Device role | Role assigned to synchronized devices (defaults to `VMware Node`). |
| Manufacturer | Manufacturer for auto-created device types (defaults to `VMware`). |
| Virtualization cluster | NetBox cluster for synchronized virtual machines. |
| Delete stale objects | Delete NetBox objects that no longer exist on the endpoint. |

## REST API

The plugin exposes read/write API endpoints under `/api/plugins/vmware/`:

```
GET    /api/plugins/vmware/clusters/
POST   /api/plugins/vmware/clusters/{id}/sync/
GET    /api/plugins/vmware/hosts/
GET    /api/plugins/vmware/vms/
GET    /api/plugins/vmware/disks/
```

## Security notes

* Passwords are stored encrypted using a key derived from NetBox's `SECRET_KEY`.
  Rotating `SECRET_KEY` invalidates stored passwords (re-enter them afterwards).
* Passwords are never returned by the UI or the REST API.

## Development

```bash
pip install -e .
python manage.py makemigrations netbox_vmware   # only if models change
```
