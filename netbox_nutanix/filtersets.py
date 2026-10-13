from django.db.models import Q

from netbox.filtersets import NetBoxModelFilterSet

from .models import NutanixCluster, NutanixDisk, NutanixHost, NutanixVirtualMachine


class NutanixClusterFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = NutanixCluster
        fields = ('id', 'name', 'enabled', 'deployment', 'base_url', 'site_id', 'cluster_id')

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(name__icontains=value) | Q(base_url__icontains=value) | Q(username__icontains=value)
        )


class NutanixHostFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = NutanixHost
        fields = ('id', 'name', 'uuid', 'cluster_id', 'netbox_device_id')

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(Q(name__icontains=value) | Q(serial__icontains=value))


class NutanixVirtualMachineFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = NutanixVirtualMachine
        fields = ('id', 'name', 'uuid', 'power_state', 'cluster_id', 'netbox_vm_id')

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(name__icontains=value)


class NutanixDiskFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = NutanixDisk
        fields = ('id', 'uuid', 'device_index', 'adapter_type', 'virtual_machine_id')

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(adapter_type__icontains=value) | Q(storage_container__icontains=value)
        )
