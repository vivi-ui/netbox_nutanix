from rest_framework import serializers

from dcim.api.serializers import (
    DeviceRoleSerializer,
    DeviceSerializer,
    DeviceTypeSerializer,
    ManufacturerSerializer,
    SiteSerializer,
)
from netbox.api.serializers import ValidatedModelSerializer
from tenancy.api.serializers import TenantSerializer

from ..models import SnmpDevice, SnmpEndpoint, SnmpTarget


class SnmpEndpointSerializer(ValidatedModelSerializer):
    community = serializers.CharField(write_only=True, required=False, allow_blank=True)
    auth_key = serializers.CharField(write_only=True, required=False, allow_blank=True)
    priv_key = serializers.CharField(write_only=True, required=False, allow_blank=True)
    site = SiteSerializer(nested=True)
    device_role = DeviceRoleSerializer(nested=True, required=False, allow_null=True)
    manufacturer = ManufacturerSerializer(nested=True, required=False, allow_null=True)
    device_type = DeviceTypeSerializer(nested=True, required=False, allow_null=True)
    tenant = TenantSerializer(nested=True, required=False, allow_null=True)

    class Meta:
        model = SnmpEndpoint
        fields = (
            'id', 'url', 'display_url', 'display', 'name', 'enabled', 'snmp_version',
            'community', 'security_username', 'security_level', 'auth_protocol', 'auth_key',
            'priv_protocol', 'priv_key', 'port', 'timeout', 'retries', 'site', 'device_role',
            'manufacturer', 'device_type', 'tenant', 'delete_stale', 'quick_discovery',
            'discover_neighbors', 'create_cables', 'max_depth', 'max_devices',
            'collect_vlans', 'infer_prefixes',
            'collect_arp', 'collect_fdb', 'max_arp_entries', 'collect_modules',
            'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'enabled', 'snmp_version')

    def _apply_secrets(self, instance):
        for field in ('community', 'auth_key', 'priv_key'):
            raw = self.validated_data.pop(field, None)
            if raw:
                getattr(instance, f'set_{field}')(raw)

    def create(self, validated_data):
        instance = super().create(validated_data)
        self._apply_secrets(instance)
        if any((instance.community, instance.auth_key, instance.priv_key)):
            instance.save()
        return instance

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        self._apply_secrets(instance)
        instance.save()
        return instance


class SnmpTargetSerializer(ValidatedModelSerializer):
    class Meta:
        model = SnmpTarget
        fields = (
            'id', 'url', 'display_url', 'display', 'endpoint', 'address', 'enabled',
            'description', 'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'endpoint', 'address', 'enabled')


class SnmpDeviceSerializer(ValidatedModelSerializer):
    netbox_device = DeviceSerializer(nested=True, required=False, allow_null=True)

    class Meta:
        model = SnmpDevice
        fields = (
            'id', 'url', 'display_url', 'display', 'endpoint', 'address', 'sys_name',
            'sys_object_id', 'sys_descr', 'sys_location', 'sys_contact', 'serial', 'uptime',
            'netbox_device', 'last_synced', 'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'endpoint', 'address', 'sys_name')
