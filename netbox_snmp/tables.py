import django_tables2 as tables

from netbox.tables import ActionsColumn, NetBoxTable

from .models import SnmpDevice, SnmpEndpoint, SnmpTarget

# Devices are managed by the discovery job and cannot be edited through the UI,
# so their action column omits the (missing) edit link.
READ_ONLY_ACTIONS = ActionsColumn(actions=('delete', 'changelog'))


class SnmpEndpointTable(NetBoxTable):
    name = tables.Column(linkify=True)
    site = tables.Column(linkify=True)
    device_role = tables.Column(linkify=True)
    manufacturer = tables.Column(linkify=True)
    device_type = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = SnmpEndpoint
        fields = (
            'pk', 'name', 'enabled', 'snmp_version', 'site', 'device_role',
            'manufacturer', 'discover_neighbors', 'delete_stale', 'last_updated',
        )
        default_columns = (
            'name', 'enabled', 'snmp_version', 'site', 'device_role',
            'discover_neighbors', 'delete_stale',
        )


class SnmpTargetTable(NetBoxTable):
    address = tables.Column(linkify=True)
    endpoint = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = SnmpTarget
        fields = ('pk', 'address', 'endpoint', 'enabled', 'description', 'last_updated')
        default_columns = ('address', 'endpoint', 'enabled', 'description')


class SnmpDeviceTable(NetBoxTable):
    sys_name = tables.Column(linkify=True)
    endpoint = tables.Column(linkify=True)
    netbox_device = tables.Column(linkify=True)
    actions = READ_ONLY_ACTIONS

    class Meta(NetBoxTable.Meta):
        model = SnmpDevice
        fields = (
            'pk', 'sys_name', 'endpoint', 'address', 'serial', 'netbox_device', 'last_synced',
        )
        default_columns = (
            'sys_name', 'endpoint', 'address', 'serial', 'netbox_device', 'last_synced',
        )
