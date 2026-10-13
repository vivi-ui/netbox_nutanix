from django import forms

from dcim.models import DeviceRole, Manufacturer, Site
from tenancy.models import Tenant
from virtualization.models import Cluster

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

from .choices import VMwareDeploymentChoices
from .models import VMwareEndpoint, VMwareDisk, VMwareHost, VMwareVirtualMachine


class VMwareEndpointForm(NetBoxModelForm):
    password = forms.CharField(
        label='Password',
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={'autocomplete': 'new-password'}),
        help_text='Stored encrypted. Leave blank to keep the existing password.',
    )
    site = DynamicModelChoiceField(queryset=Site.objects.all())
    device_role = DynamicModelChoiceField(queryset=DeviceRole.objects.all(), required=False)
    manufacturer = DynamicModelChoiceField(queryset=Manufacturer.objects.all(), required=False)
    cluster = DynamicModelChoiceField(queryset=Cluster.objects.all(), required=False)
    tenant = DynamicModelChoiceField(queryset=Tenant.objects.all(), required=False)

    class Meta:
        model = VMwareEndpoint
        fields = (
            'name', 'enabled', 'deployment', 'base_url', 'username', 'verify_ssl', 'timeout',
            'site', 'device_role', 'manufacturer', 'cluster', 'tenant', 'delete_stale',
        )

    fieldsets = (
        FieldSet('name', 'enabled', 'deployment', name='Endpoint'),
        FieldSet('base_url', 'username', 'password', 'verify_ssl', 'timeout', name='Connection'),
        FieldSet(
            'site', 'device_role', 'manufacturer', 'cluster', 'tenant', 'delete_stale',
            name='Synchronization defaults',
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            # Never render the stored (encrypted) password back to the browser.
            self.fields['password'].required = False
        else:
            self.fields['password'].required = True

    def save(self, commit=True):
        instance = super().save(commit=False)
        raw_password = self.cleaned_data.get('password')
        if raw_password:
            instance.set_password(raw_password)
        if commit:
            instance.save()
        return instance


class VMwareEndpointBulkEditForm(NetBoxModelBulkEditForm):
    model = VMwareEndpoint

    enabled = forms.NullBooleanField(
        required=False,
        label='Enabled',
        widget=forms.Select(choices=BOOLEAN_WITH_BLANK_CHOICES),
    )
    verify_ssl = forms.NullBooleanField(
        required=False,
        label='Verify SSL',
        widget=forms.Select(choices=BOOLEAN_WITH_BLANK_CHOICES),
    )
    delete_stale = forms.NullBooleanField(
        required=False,
        label='Delete stale objects',
        widget=forms.Select(choices=BOOLEAN_WITH_BLANK_CHOICES),
    )
    timeout = forms.IntegerField(required=False, min_value=1, label='Timeout (s)')
    device_role = DynamicModelChoiceField(queryset=DeviceRole.objects.all(), required=False)
    tenant = DynamicModelChoiceField(queryset=Tenant.objects.all(), required=False)

    fieldsets = (
        FieldSet('enabled', 'verify_ssl', 'timeout', 'delete_stale'),
        FieldSet('device_role', 'tenant', name='Synchronization defaults'),
    )
    nullable_fields = ('device_role', 'tenant')


class VMwareEndpointImportForm(NetBoxModelImportForm):
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
    cluster = CSVModelChoiceField(
        queryset=Cluster.objects.all(),
        to_field_name='name',
        required=False,
        help_text='Assigned virtualization cluster (name)',
    )
    tenant = CSVModelChoiceField(
        queryset=Tenant.objects.all(),
        to_field_name='name',
        required=False,
        help_text='Assigned tenant (name)',
    )

    class Meta:
        model = VMwareEndpoint
        # Passwords cannot be imported in plaintext via CSV; set them from the UI afterwards.
        fields = (
            'name', 'enabled', 'deployment', 'base_url', 'username', 'verify_ssl', 'timeout',
            'site', 'device_role', 'manufacturer', 'cluster', 'tenant', 'delete_stale',
        )


class VMwareEndpointFilterForm(NetBoxModelFilterSetForm):
    model = VMwareEndpoint

    name = forms.CharField(required=False)
    enabled = forms.NullBooleanField(
        required=False,
        widget=forms.Select(choices=BOOLEAN_WITH_BLANK_CHOICES),
    )
    deployment = forms.MultipleChoiceField(choices=VMwareDeploymentChoices, required=False)
    site_id = DynamicModelMultipleChoiceField(queryset=Site.objects.all(), required=False, label='Site')
    cluster_id = DynamicModelMultipleChoiceField(
        queryset=Cluster.objects.all(), required=False, label='Virtualization cluster'
    )

    fieldsets = (
        FieldSet('name', 'enabled', 'deployment'),
        FieldSet('site_id', 'cluster_id', name='Scope'),
    )


class VMwareHostFilterForm(NetBoxModelFilterSetForm):
    model = VMwareHost

    name = forms.CharField(required=False)
    cluster_id = DynamicModelMultipleChoiceField(
        queryset=VMwareEndpoint.objects.all(), required=False, label='VMware endpoint'
    )

    fieldsets = (FieldSet('name', 'cluster_id'),)


class VMwareVirtualMachineFilterForm(NetBoxModelFilterSetForm):
    model = VMwareVirtualMachine

    name = forms.CharField(required=False)
    power_state = forms.CharField(required=False, label='Power state')
    cluster_id = DynamicModelMultipleChoiceField(
        queryset=VMwareEndpoint.objects.all(), required=False, label='VMware endpoint'
    )

    fieldsets = (FieldSet('name', 'power_state', 'cluster_id'),)


class VMwareDiskFilterForm(NetBoxModelFilterSetForm):
    model = VMwareDisk

    virtual_machine_id = DynamicModelMultipleChoiceField(
        queryset=VMwareVirtualMachine.objects.all(),
        required=False,
        label='VMware virtual machine',
    )
    adapter_type = forms.CharField(required=False, label='Adapter type')

    fieldsets = (FieldSet('virtual_machine_id', 'adapter_type'),)
