# netbox-nutanix

A NetBox plugin that synchronizes **Nutanix** infrastructure into NetBox:

* Nutanix **hosts** (hypervisor nodes) are reconciled as `dcim.Device` objects,
  including their network interfaces (`dcim.Interface`), MAC addresses
  (`dcim.MACAddress`) and assigned IP addresses (`ipam.IPAddress`).
* Nutanix **virtual machines** are reconciled as `virtualization.VirtualMachine`
  objects, including their network interfaces (`virtualization.VMInterface`),
  assigned IP addresses and per-disk records (`NutanixDisk`).

The plugin talks to the Nutanix REST API (Prism Central v3 or Prism Element
v2.0), stores the discovered objects in its own tables so that mappings can be
tracked over time, and runs synchronization as a background job.

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
    'netbox_nutanix',
]
```

Optional plugin settings:

```python
PLUGINS_CONFIG = {
    'netbox_nutanix': {
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
python manage.py migrate netbox_nutanix
sudo systemctl restart netbox netbox-rq
```

## Usage

1. Navigate to **Nutanix > Endpoints** and add an endpoint with the Prism URL,
   credentials and synchronization defaults (site, device role, virtualization
   cluster).
2. Open the endpoint and click **Sync now**. A background job is enqueued; open
   the entry under the **Jobs** tab to watch progress.
3. Discovered hosts appear under **Nutanix > Hosts** and virtual machines under
   **Nutanix > Virtual Machines**. Each record links to the corresponding
   NetBox device or virtual machine. Virtual machine disks are listed under
   **Nutanix > Disks** and beneath each virtual machine.

### Endpoint options

| Field | Description |
|-------|-------------|
| Deployment | `Prism Central` (REST v3) or `Prism Element` (REST v2.0). |
| Base URL | e.g. `https://prism-central.example.com:9440` |
| Verify SSL | Disable for self-signed certificates (not recommended). |
| Site | Site assigned to synchronized devices. |
| Device role | Role assigned to synchronized devices (defaults to `Nutanix Node`). |
| Manufacturer | Manufacturer for auto-created device types (defaults to `Nutanix`). |
| Virtualization cluster | NetBox cluster for synchronized virtual machines. |
| Delete stale objects | Delete NetBox objects that no longer exist on the endpoint. |

## REST API

The plugin exposes read/write API endpoints under `/api/plugins/nutanix/`:

```
GET    /api/plugins/nutanix/clusters/
POST   /api/plugins/nutanix/clusters/{id}/sync/
GET    /api/plugins/nutanix/hosts/
GET    /api/plugins/nutanix/vms/
GET    /api/plugins/nutanix/disks/
```

## Security notes

* Passwords are stored encrypted using a key derived from NetBox's `SECRET_KEY`.
  Rotating `SECRET_KEY` invalidates stored passwords (re-enter them afterwards).
* Passwords are never returned by the UI or the REST API.

## Development

```bash
pip install -e .
python manage.py makemigrations netbox_nutanix   # only if models change
```
