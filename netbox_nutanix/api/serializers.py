from rest_framework import serializers

from dcim.api.serializers import DeviceSerializer, DeviceRoleSerializer, ManufacturerSerializer, SiteSerializer
from netbox.api.serializers import ValidatedModelSerializer
from tenancy.api.serializers import TenantSerializer
from virtualization.api.serializers import ClusterSerializer, VirtualMachineSerializer

from ..models import NutanixCluster, NutanixDisk, NutanixHost, NutanixVirtualMachine


class NutanixClusterSerializer(ValidatedModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    site = SiteSerializer(nested=True)
    device_role = DeviceRoleSerializer(nested=True, required=False, allow_null=True)
    manufacturer = ManufacturerSerializer(nested=True, required=False, allow_null=True)
    cluster = ClusterSerializer(nested=True, required=False, allow_null=True)
    tenant = TenantSerializer(nested=True, required=False, allow_null=True)

    class Meta:
        model = NutanixCluster
        fields = (
            'id', 'url', 'display_url', 'display', 'name', 'enabled', 'deployment', 'base_url',
            'username', 'password', 'verify_ssl', 'timeout', 'site', 'device_role',
            'manufacturer', 'cluster', 'tenant', 'delete_stale', 'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'enabled', 'deployment', 'base_url')

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        instance = super().create(validated_data)
        if password:
            instance.set_password(password)
            instance.save()
        return instance

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        instance = super().update(instance, validated_data)
        if password:
            instance.set_password(password)
            instance.save()
        return instance


class NutanixHostSerializer(ValidatedModelSerializer):
    netbox_device = DeviceSerializer(nested=True, required=False, allow_null=True)

    class Meta:
        model = NutanixHost
        fields = (
            'id', 'url', 'display_url', 'display', 'cluster', 'uuid', 'name', 'serial',
            'ip_address', 'netbox_device', 'last_synced', 'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'uuid')


class NutanixDiskSerializer(ValidatedModelSerializer):
    class Meta:
        model = NutanixDisk
        fields = (
            'id', 'url', 'display_url', 'display', 'virtual_machine', 'uuid', 'device_index',
            'adapter_type', 'size_bytes', 'storage_container', 'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'virtual_machine', 'device_index', 'size_bytes')


class NutanixVirtualMachineSerializer(ValidatedModelSerializer):
    netbox_vm = VirtualMachineSerializer(nested=True, required=False, allow_null=True)
    disks = NutanixDiskSerializer(many=True, read_only=True)

    class Meta:
        model = NutanixVirtualMachine
        fields = (
            'id', 'url', 'display_url', 'display', 'cluster', 'uuid', 'name', 'power_state',
            'vcpus', 'memory_mb', 'disk_gb', 'host_uuid', 'netbox_vm', 'disks', 'last_synced',
            'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'uuid', 'power_state')
