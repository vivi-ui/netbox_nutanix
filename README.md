# netbox-snmp

A NetBox plugin that discovers network devices (switches, routers, and similar
SNMP-speaking hardware) and their interfaces over SNMP, then reconciles the
results into NetBox's native `dcim` and `ipam` models.

## Features

- **SNMPv2c and SNMPv3 (USM)** — community strings or user-based security with
  MD5/SHA/SHA-2 authentication and DES/3DES/AES privacy.
- **Target polling** — poll individual addresses or entire CIDR ranges.
- **Neighbour discovery** — follow LLDP and CDP neighbours to discover adjacent
  switches, up to a configurable depth.
- **Native NetBox objects** — discovered devices become `dcim.Device` objects,
  ports become `dcim.Interface` objects (name, alias, type, speed, MTU, admin
  status, MAC address) and IPv4 addresses become `ipam.IPAddress` objects
  assigned to the matching interface and set as the device's primary address.
- **Manufacturer / device type inference** — the manufacturer is derived from
  `sysObjectID` and a device type is created automatically (both overridable).
- **Stale object cleanup** — optionally delete NetBox objects that disappeared
  from the device.

## Requirements

- NetBox 4.4.x – 4.6.x
- Python 3.10+
- `pysnmp >= 7.0.0`

## Installation

```bash
pip install netbox-snmp
```

Enable the plugin in `configuration.py`:

```python
PLUGINS = ['netbox_snmp']

PLUGINS_CONFIG = {
    'netbox_snmp': {
        # Optional: run a recurring discovery job every N minutes (0 = disabled)
        'sync_interval': 0,
        'request_timeout': 5,
        'request_retries': 2,
        'max_devices': 256,
        'discover_neighbors': True,
        'max_depth': 1,
    },
}
```

Then run the migrations:

```bash
python manage.py migrate netbox_snmp
```

## Usage

1. Create an **SNMP endpoint** (Plugins → SNMP → Endpoints) and configure the
   SNMP credentials, connection parameters and the NetBox scope (site, role,
   manufacturer, device type and tenant) that discovered objects should use.
2. Add one or more **targets**. The *Add targets* form accepts free-form input —
   one entry per line, or separated by commas/spaces — where each entry is a
   single address (`10.0.0.1`) or a network (`10.0.0.0/24`). For example:

   ```
   10.0.0.0/24
   10.0.1.5
   192.168.1.0/28, 2001:db8::/32
   ```

   Invalid entries are reported and skipped.
3. Click **Discover now** on the endpoint page (or POST to
   `/api/plugins/snmp/endpoints/<id>/sync/`) to enqueue a background job.

Discovered devices are listed under Plugins → SNMP → Devices.

## How discovery works

For every target address the plugin issues SNMP GET/WALK requests to the
following standard MIBs:

| Purpose | MIB |
| --- | --- |
| Device identity, name, location, uptime | SNMPv2-MIB (`system`) |
| Chassis serial number | ENTITY-MIB (`entPhysicalTable`) |
| Interfaces (name, alias, type, speed, MTU, MAC, admin status) | IF-MIB (`ifTable`, `ifXTable`) |
| IPv4 addresses and netmasks | IP-MIB (`ipAddrTable`) |
| Neighbour switches | LLDP-MIB (`lldpRemManAddrTable`) and CISCO-CDP-MIB (`cdpCacheTable`) |
| VLANs and interface membership (optional) | Q-BRIDGE-MIB (`dot1qVlanStaticTable`) |
| Forwarding table (optional) | BRIDGE-MIB (`dot1dTpFdbTable`) |
| ARP table (optional) | IP-MIB (`ipNetToMediaTable`) |

The IANA `ifType` and the reported speed are mapped onto NetBox interface
types. Neighbour management addresses returned by LLDP/CDP are queued for
further discovery until the configured depth (or device limit) is reached.

When **Create cables** is enabled on an endpoint, each discovered interface is
matched against the LLDP/CDP neighbour port (by interface name or MAC) once the
neighbouring device is present, and a `dcim.Cable` is created between the two
interfaces. Cables are only created for interfaces that are not already cabled,
so existing connections are never overwritten.

The following collection features are **disabled by default** and can be enabled
per endpoint:

- **Collect VLANs** reads the Q-BRIDGE-MIB static VLAN table, creating the
  `ipam.VLAN` objects and assigning each interface's untagged/tagged VLANs and
  access/tagged mode.
- **Infer prefixes** derives `ipam.Prefix` objects from layer-3 SVI interfaces
  (for example `Vlan100`) and links them to the matching VLAN.
- **Collect ARP** registers ARP neighbours as `ipam.IPAddress` objects on the
  interface that owns the MAC. **Collect forwarding table** reads the
  BRIDGE-MIB forwarding table so ARP entries can be mapped to the correct
  interface when the ARP table does not report one. The number of processed
  entries is capped by **Maximum ARP entries**.

A background worker is required for discovery jobs to run.

Long scans can be stopped gracefully from the endpoint page: **Stop** writes a
cancellation flag that the running job checks between targets and before writing
each device, so it halts at the next safe point and still records a clean result
(instead of being killed mid-write). The endpoint's job list is available under
**Jobs**.

## Security

SNMP credentials (community strings and USM passphrases) are stored encrypted
at rest using a key derived from NetBox's `SECRET_KEY`. When recreating an
endpoint, leave the credential fields blank to keep the stored values.

## Limitations

- Interface IP address discovery currently covers IPv4 (`ipAddrTable`); IPv6
  addresses are not collected.
- Cable creation requires the neighbour to be discoverable: LLDP/CDP must expose
  a management address (or the neighbour must be added as a target) so the
  adjacent device exists in NetBox before the link can be resolved.

## License

Apache-2.0
