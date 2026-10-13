import django_tables2 as tables

from netbox.tables import ActionsColumn, NetBoxTable

from .models import VMwareEndpoint, VMwareDisk, VMwareHost, VMwareVirtualMachine

# Hosts and virtual machines are managed by the synchronization job and cannot be
# edited through the UI, so their action column omits the (missing) edit link.
READ_ONLY_ACTIONS = ActionsColumn(actions=('delete', 'changelog'))


class VMwareEndpointTable(NetBoxTable):
    name = tables.Column(linkify=True)
    site = tables.Column(linkify=True)
    device_role = tables.Column(linkify=True)
    cluster = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = VMwareEndpoint
        fields = (
            'pk', 'name', 'enabled', 'deployment', 'base_url', 'site', 'cluster',
            'device_role', 'delete_stale', 'last_updated',
        )
        default_columns = (
            'name', 'enabled', 'deployment', 'base_url', 'site', 'cluster', 'delete_stale',
        )


class VMwareHostTable(NetBoxTable):
    name = tables.Column(linkify=True)
    cluster = tables.Column(linkify=True)
    netbox_device = tables.Column(linkify=True)
    actions = READ_ONLY_ACTIONS

    class Meta(NetBoxTable.Meta):
        model = VMwareHost
        fields = (
            'pk', 'name', 'cluster', 'uuid', 'serial', 'ip_address', 'netbox_device', 'last_synced',
        )
        default_columns = (
            'name', 'cluster', 'serial', 'ip_address', 'netbox_device', 'last_synced',
        )


class VMwareVirtualMachineTable(NetBoxTable):
    name = tables.Column(linkify=True)
    cluster = tables.Column(linkify=True)
    netbox_vm = tables.Column(linkify=True)
    actions = READ_ONLY_ACTIONS

    class Meta(NetBoxTable.Meta):
        model = VMwareVirtualMachine
        fields = (
            'pk', 'name', 'cluster', 'uuid', 'power_state', 'vcpus', 'memory_mb', 'disk_gb',
            'netbox_vm', 'last_synced',
        )
        default_columns = (
            'name', 'cluster', 'power_state', 'vcpus', 'memory_mb', 'disk_gb', 'netbox_vm',
            'last_synced',
        )


class VMwareDiskTable(NetBoxTable):
    virtual_machine = tables.Column(linkify=True, verbose_name='Virtual machine')
    size_gib = tables.Column(verbose_name='Size (GiB)')
    actions = READ_ONLY_ACTIONS

    class Meta(NetBoxTable.Meta):
        model = VMwareDisk
        fields = (
            'pk', 'virtual_machine', 'uuid', 'device_index', 'adapter_type', 'size_gib',
            'storage_container', 'last_updated',
        )
        default_columns = (
            'virtual_machine', 'device_index', 'adapter_type', 'size_gib', 'storage_container',
        )
