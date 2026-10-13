from django.db.models import Q

from netbox.filtersets import NetBoxModelFilterSet

from .models import SnmpDevice, SnmpEndpoint, SnmpTarget


class SnmpEndpointFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = SnmpEndpoint
        fields = (
            'id', 'name', 'enabled', 'snmp_version', 'site_id', 'device_role_id',
            'manufacturer_id', 'device_type_id', 'discover_neighbors',
        )

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(name__icontains=value) | Q(security_username__icontains=value)
        )


class SnmpTargetFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = SnmpTarget
        fields = ('id', 'endpoint_id', 'address', 'enabled')

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(address__icontains=value) | Q(description__icontains=value)
        )


class SnmpDeviceFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = SnmpDevice
        fields = ('id', 'endpoint_id', 'address', 'sys_name', 'netbox_device_id')

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(sys_name__icontains=value)
            | Q(address__icontains=value)
            | Q(sys_descr__icontains=value)
            | Q(serial__icontains=value)
        )
