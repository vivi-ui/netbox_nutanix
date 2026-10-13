import django_tables2 as tables

from netbox.tables import ActionsColumn, NetBoxTable

from .models import NutanixCluster, NutanixDisk, NutanixHost, NutanixVirtualMachine

# Hosts and virtual machines are managed by the synchronization job and cannot be
# edited through the UI, so their action column omits the (missing) edit link.
READ_ONLY_ACTIONS = ActionsColumn(actions=('delete', 'changelog'))


class NutanixClusterTable(NetBoxTable):
    name = tables.Column(linkify=True)
    site = tables.Column(linkify=True)
    device_role = tables.Column(linkify=True)
    cluster = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = NutanixCluster
        fields = (
            'pk', 'name', 'enabled', 'deployment', 'base_url', 'site', 'cluster',
            'device_role', 'delete_stale', 'last_updated',
        )
        default_columns = (
            'name', 'enabled', 'deployment', 'base_url', 'site', 'cluster', 'delete_stale',
        )


class NutanixHostTable(NetBoxTable):
    name = tables.Column(linkify=True)
    cluster = tables.Column(linkify=True)
    netbox_device = tables.Column(linkify=True)
    actions = READ_ONLY_ACTIONS

    class Meta(NetBoxTable.Meta):
        model = NutanixHost
        fields = (
            'pk', 'name', 'cluster', 'uuid', 'serial', 'ip_address', 'netbox_device', 'last_synced',
        )
        default_columns = (
            'name', 'cluster', 'serial', 'ip_address', 'netbox_device', 'last_synced',
        )


class NutanixVirtualMachineTable(NetBoxTable):
    name = tables.Column(linkify=True)
    cluster = tables.Column(linkify=True)
    netbox_vm = tables.Column(linkify=True)
    actions = READ_ONLY_ACTIONS

    class Meta(NetBoxTable.Meta):
        model = NutanixVirtualMachine
        fields = (
            'pk', 'name', 'cluster', 'uuid', 'power_state', 'vcpus', 'memory_mb', 'disk_gb',
            'netbox_vm', 'last_synced',
        )
        default_columns = (
            'name', 'cluster', 'power_state', 'vcpus', 'memory_mb', 'disk_gb', 'netbox_vm',
            'last_synced',
        )


class NutanixDiskTable(NetBoxTable):
    virtual_machine = tables.Column(linkify=True, verbose_name='Virtual machine')
    size_gb = tables.Column(verbose_name='Size (GB)')
    actions = READ_ONLY_ACTIONS

    class Meta(NetBoxTable.Meta):
        model = NutanixDisk
        fields = (
            'pk', 'virtual_machine', 'uuid', 'device_index', 'adapter_type', 'size_gb',
            'storage_container', 'last_updated',
        )
        default_columns = (
            'virtual_machine', 'device_index', 'adapter_type', 'size_gb', 'storage_container',
        )
