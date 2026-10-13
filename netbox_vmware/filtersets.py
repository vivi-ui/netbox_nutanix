from django.db.models import Q

from netbox.filtersets import NetBoxModelFilterSet

from .models import VMwareEndpoint, VMwareDisk, VMwareHost, VMwareVirtualMachine


class VMwareEndpointFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = VMwareEndpoint
        fields = ('id', 'name', 'enabled', 'deployment', 'base_url', 'site_id', 'cluster_id')

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(name__icontains=value) | Q(base_url__icontains=value) | Q(username__icontains=value)
        )


class VMwareHostFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = VMwareHost
        fields = ('id', 'name', 'uuid', 'cluster_id', 'netbox_device_id')

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(Q(name__icontains=value) | Q(serial__icontains=value))


class VMwareVirtualMachineFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = VMwareVirtualMachine
        fields = ('id', 'name', 'uuid', 'power_state', 'cluster_id', 'netbox_vm_id')

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(name__icontains=value)


class VMwareDiskFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = VMwareDisk
        fields = ('id', 'uuid', 'device_index', 'adapter_type', 'virtual_machine_id')

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(adapter_type__icontains=value) | Q(storage_container__icontains=value)
        )
