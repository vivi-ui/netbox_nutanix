from django import forms

from dcim.models import DeviceRole, DeviceType, Manufacturer, Site
from tenancy.models import Tenant

from netbox.forms import (
    NetBoxModelBulkEditForm,
    NetBoxModelFilterSetForm,
    NetBoxModelForm,
    NetBoxModelImportForm,
)
from utilities.forms import BOOLEAN_WITH_BLANK_CHOICES
from utilities.forms.fields import (
    CSVModelChoiceField,
    DynamicModelChoiceField,
    DynamicModelMultipleChoiceField,
)
from utilities.forms.rendering import FieldSet

from .choices import (
    SnmpAuthProtocolChoices,
    SnmpPrivProtocolChoices,
    SnmpSecurityLevelChoices,
    SnmpVersionChoices,
)
from .models import SnmpDevice, SnmpEndpoint, SnmpTarget


class SnmpEndpointForm(NetBoxModelForm):
    community = forms.CharField(
        label='Community',
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={'autocomplete': 'new-password'}),
        help_text='Stored encrypted. Leave blank to keep the existing value.',
    )
    auth_key = forms.CharField(
        label='Authentication key',
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={'autocomplete': 'new-password'}),
        help_text='Stored encrypted. Leave blank to keep the existing value.',
    )
    priv_key = forms.CharField(
        label='Privacy key',
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={'autocomplete': 'new-password'}),
        help_text='Stored encrypted. Leave blank to keep the existing value.',
    )
    site = DynamicModelChoiceField(queryset=Site.objects.all())
    device_role = DynamicModelChoiceField(queryset=DeviceRole.objects.all(), required=False)
    manufacturer = DynamicModelChoiceField(queryset=Manufacturer.objects.all(), required=False)
    device_type = DynamicModelChoiceField(queryset=DeviceType.objects.all(), required=False)
    tenant = DynamicModelChoiceField(queryset=Tenant.objects.all(), required=False)

    class Meta:
        model = SnmpEndpoint
        fields = (
            'name', 'enabled',
            'snmp_version', 'community', 'security_username', 'security_level',
            'auth_protocol', 'auth_key', 'priv_protocol', 'priv_key',
            'port', 'timeout', 'retries',
            'site', 'device_role', 'manufacturer', 'device_type', 'tenant', 'delete_stale',
            'discover_neighbors', 'create_cables', 'max_depth', 'max_devices',
            'collect_vlans', 'infer_prefixes', 'collect_arp', 'collect_fdb', 'max_arp_entries',
            'collect_modules',
        )

    fieldsets = (
        FieldSet('name', 'enabled', name='Endpoint'),
        FieldSet(
            'snmp_version', 'community',
            name='SNMPv2c credentials',
        ),
        FieldSet(
            'security_username', 'security_level', 'auth_protocol', 'auth_key',
            'priv_protocol', 'priv_key',
            name='SNMPv3 credentials',
        ),
        FieldSet('port', 'timeout', 'retries', name='Connection'),
        FieldSet(
            'site', 'device_role', 'manufacturer', 'device_type', 'tenant', 'delete_stale',
            name='Synchronization defaults',
        ),
        FieldSet(
            'discover_neighbors', 'create_cables', 'max_depth', 'max_devices',
            name='Neighbor discovery',
        ),
        FieldSet(
            'collect_vlans', 'infer_prefixes', 'collect_arp', 'collect_fdb', 'max_arp_entries',
            name='VLAN / ARP collection',
        ),
        FieldSet('collect_modules', name='Hardware modules'),
    )

    def save(self, commit=True):
        instance = super().save(commit=False)
        for field in ('community', 'auth_key', 'priv_key'):
            raw = self.cleaned_data.get(field)
            if raw:
                getattr(instance, f'set_{field}')(raw)
        if commit:
            instance.save()
        return instance


class SnmpEndpointBulkEditForm(NetBoxModelBulkEditForm):
    model = SnmpEndpoint

    enabled = forms.NullBooleanField(
        required=False,
        label='Enabled',
        widget=forms.Select(choices=BOOLEAN_WITH_BLANK_CHOICES),
    )
    delete_stale = forms.NullBooleanField(
        required=False,
        label='Delete stale objects',
        widget=forms.Select(choices=BOOLEAN_WITH_BLANK_CHOICES),
    )
    discover_neighbors = forms.NullBooleanField(
        required=False,
        label='Discover neighbors',
        widget=forms.Select(choices=BOOLEAN_WITH_BLANK_CHOICES),
    )
    create_cables = forms.NullBooleanField(
        required=False,
        label='Create cables',
        widget=forms.Select(choices=BOOLEAN_WITH_BLANK_CHOICES),
    )
    collect_vlans = forms.NullBooleanField(
        required=False,
        label='Collect VLANs',
        widget=forms.Select(choices=BOOLEAN_WITH_BLANK_CHOICES),
    )
    infer_prefixes = forms.NullBooleanField(
        required=False,
        label='Infer prefixes',
        widget=forms.Select(choices=BOOLEAN_WITH_BLANK_CHOICES),
    )
    collect_arp = forms.NullBooleanField(
        required=False,
        label='Collect ARP',
        widget=forms.Select(choices=BOOLEAN_WITH_BLANK_CHOICES),
    )
    collect_fdb = forms.NullBooleanField(
        required=False,
        label='Collect FDB',
        widget=forms.Select(choices=BOOLEAN_WITH_BLANK_CHOICES),
    )
    collect_modules = forms.NullBooleanField(
        required=False,
        label='Collect modules',
        widget=forms.Select(choices=BOOLEAN_WITH_BLANK_CHOICES),
    )
    timeout = forms.IntegerField(required=False, min_value=1, label='Timeout (s)')
    retries = forms.IntegerField(required=False, min_value=0, label='Retries')
    max_arp_entries = forms.IntegerField(required=False, min_value=1, label='Max ARP entries')
    device_role = DynamicModelChoiceField(queryset=DeviceRole.objects.all(), required=False)
    tenant = DynamicModelChoiceField(queryset=Tenant.objects.all(), required=False)

    fieldsets = (
        FieldSet('enabled', 'timeout', 'retries', 'delete_stale', 'discover_neighbors', 'create_cables'),
        FieldSet('collect_vlans', 'infer_prefixes', 'collect_arp', 'collect_fdb', 'max_arp_entries',
                 name='VLAN / ARP collection'),
        FieldSet('collect_modules', name='Hardware modules'),
        FieldSet('device_role', 'tenant', name='Synchronization defaults'),
    )
    nullable_fields = ('device_role', 'tenant')


class SnmpEndpointImportForm(NetBoxModelImportForm):
    site = CSVModelChoiceField(
        queryset=Site.objects.all(),
        to_field_name='name',
        help_text='Assigned site (name)',
    )
    device_role = CSVModelChoiceField(
        queryset=DeviceRole.objects.all(),
        to_field_name='name',
        required=False,
        help_text='Assigned device role (name)',
    )
    manufacturer = CSVModelChoiceField(
        queryset=Manufacturer.objects.all(),
        to_field_name='name',
        required=False,
        help_text='Assigned manufacturer (name)',
    )
    device_type = CSVModelChoiceField(
        queryset=DeviceType.objects.all(),
        to_field_name='model',
        required=False,
        help_text='Assigned device type (model)',
    )
    tenant = CSVModelChoiceField(
        queryset=Tenant.objects.all(),
        to_field_name='name',
        required=False,
        help_text='Assigned tenant (name)',
    )

    class Meta:
        model = SnmpEndpoint
        # Secrets cannot be imported in plaintext via CSV; set them from the UI afterwards.
        fields = (
            'name', 'enabled', 'snmp_version', 'security_username', 'security_level',
            'auth_protocol', 'priv_protocol', 'port', 'timeout', 'retries',
            'site', 'device_role', 'manufacturer', 'device_type', 'tenant', 'delete_stale',
            'discover_neighbors', 'create_cables', 'max_depth', 'max_devices',
            'collect_vlans', 'infer_prefixes', 'collect_arp', 'collect_fdb', 'max_arp_entries',
            'collect_modules',
        )


class SnmpTargetForm(NetBoxModelForm):
    endpoint = DynamicModelChoiceField(queryset=SnmpEndpoint.objects.all())

    class Meta:
        model = SnmpTarget
        fields = ('endpoint', 'address', 'enabled', 'description')


class SnmpTargetMultiAddForm(forms.Form):
    """
    Accepts one or more addresses/networks and creates a target for each.
    """

    endpoint = DynamicModelChoiceField(
        queryset=SnmpEndpoint.objects.all(),
        label='SNMP endpoint',
    )
    addresses = forms.CharField(
        label='Addresses / networks',
        widget=forms.Textarea(attrs={'rows': 8, 'class': 'font-monospace'}),
        help_text=(
            "One IPv4/IPv6 address or CIDR network per line. "
            "Commas or spaces may also be used as separators, e.g. "
            "10.0.0.0/24, 10.0.1.5, 192.168.1.0/28"
        ),
    )
    enabled = forms.BooleanField(
        required=False,
        initial=True,
        label='Enabled',
    )
    description = forms.CharField(
        required=False,
        max_length=200,
    )


class SnmpTargetBulkEditForm(NetBoxModelBulkEditForm):
    model = SnmpTarget

    endpoint = DynamicModelChoiceField(queryset=SnmpEndpoint.objects.all(), required=False)
    enabled = forms.NullBooleanField(
        required=False,
        widget=forms.Select(choices=BOOLEAN_WITH_BLANK_CHOICES),
    )

    fieldsets = (FieldSet('endpoint', 'enabled'),)


class SnmpTargetImportForm(NetBoxModelImportForm):
    endpoint = CSVModelChoiceField(
        queryset=SnmpEndpoint.objects.all(),
        to_field_name='name',
        help_text='SNMP endpoint (name)',
    )

    class Meta:
        model = SnmpTarget
        fields = ('endpoint', 'address', 'enabled', 'description')


class SnmpEndpointFilterForm(NetBoxModelFilterSetForm):
    model = SnmpEndpoint

    name = forms.CharField(required=False)
    enabled = forms.NullBooleanField(
        required=False,
        widget=forms.Select(choices=BOOLEAN_WITH_BLANK_CHOICES),
    )
    snmp_version = forms.MultipleChoiceField(choices=SnmpVersionChoices, required=False)
    site_id = DynamicModelMultipleChoiceField(queryset=Site.objects.all(), required=False, label='Site')

    fieldsets = (FieldSet('name', 'enabled', 'snmp_version', 'site_id'),)


class SnmpTargetFilterForm(NetBoxModelFilterSetForm):
    model = SnmpTarget

    address = forms.CharField(required=False)
    endpoint_id = DynamicModelMultipleChoiceField(
        queryset=SnmpEndpoint.objects.all(), required=False, label='SNMP endpoint'
    )
    enabled = forms.NullBooleanField(
        required=False,
        widget=forms.Select(choices=BOOLEAN_WITH_BLANK_CHOICES),
    )

    fieldsets = (FieldSet('address', 'endpoint_id', 'enabled'),)


class SnmpDeviceFilterForm(NetBoxModelFilterSetForm):
    model = SnmpDevice

    sys_name = forms.CharField(required=False, label='System name')
    address = forms.CharField(required=False)
    endpoint_id = DynamicModelMultipleChoiceField(
        queryset=SnmpEndpoint.objects.all(), required=False, label='SNMP endpoint'
    )

    fieldsets = (FieldSet('sys_name', 'address', 'endpoint_id'),)
