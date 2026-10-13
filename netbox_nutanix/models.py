from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox.models import NetBoxModel
from netbox.models.features import JobsMixin

from .choices import NutanixDeploymentChoices
from .crypto import decrypt, encrypt


class NutanixCluster(JobsMixin, NetBoxModel):
    """
    Connection and synchronization configuration for a single Nutanix Prism endpoint.

    Each endpoint stores the credentials used to query the API together with the
    NetBox objects that newly discovered hosts and virtual machines should be
    associated with.
    """

    name = models.CharField(
        verbose_name=_('name'),
        max_length=100,
        unique=True,
    )
    enabled = models.BooleanField(
        verbose_name=_('enabled'),
        default=True,
    )
    deployment = models.CharField(
        verbose_name=_('deployment'),
        max_length=10,
        choices=NutanixDeploymentChoices,
        default=NutanixDeploymentChoices.PRISM_CENTRAL,
        help_text=_("Whether the endpoint is a Prism Central or Prism Element instance."),
    )
    base_url = models.URLField(
        verbose_name=_('base URL'),
        max_length=255,
        help_text=_("Prism endpoint, e.g. https://prism-central.example.com:9440"),
    )
    username = models.CharField(
        verbose_name=_('username'),
        max_length=150,
    )
    password = models.CharField(
        verbose_name=_('password'),
        max_length=500,
        blank=True,
        help_text=_("Stored encrypted. Leave blank to keep the existing password."),
    )
    verify_ssl = models.BooleanField(
        verbose_name=_('verify SSL'),
        default=True,
    )
    timeout = models.PositiveIntegerField(
        verbose_name=_('timeout'),
        default=30,
        help_text=_("Request timeout in seconds."),
    )

    site = models.ForeignKey(
        to='dcim.Site',
        on_delete=models.PROTECT,
        related_name='+',
        verbose_name=_('site'),
    )
    device_role = models.ForeignKey(
        to='dcim.DeviceRole',
        on_delete=models.SET_NULL,
        related_name='+',
        blank=True,
        null=True,
        verbose_name=_('device role'),
        help_text=_("Role assigned to synchronized hosts. Defaults to 'Nutanix Node' when unset."),
    )
    manufacturer = models.ForeignKey(
        to='dcim.Manufacturer',
        on_delete=models.SET_NULL,
        related_name='+',
        blank=True,
        null=True,
        verbose_name=_('manufacturer'),
        help_text=_("Manufacturer assigned to synchronized device types. Defaults to 'Nutanix'."),
    )
    cluster = models.ForeignKey(
        to='virtualization.Cluster',
        on_delete=models.SET_NULL,
        related_name='+',
        blank=True,
        null=True,
        verbose_name=_('virtualization cluster'),
        help_text=_("NetBox cluster under which synchronized virtual machines are created."),
    )
    tenant = models.ForeignKey(
        to='tenancy.Tenant',
        on_delete=models.SET_NULL,
        related_name='+',
        blank=True,
        null=True,
        verbose_name=_('tenant'),
    )
    delete_stale = models.BooleanField(
        verbose_name=_('delete stale objects'),
        default=False,
        help_text=_("Delete NetBox objects no longer present on the Nutanix endpoint."),
    )

    class Meta:
        verbose_name = _('Nutanix endpoint')
        verbose_name_plural = _('Nutanix endpoints')
        ordering = ('name',)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('plugins:netbox_nutanix:nutanixcluster', args=[self.pk])

    def set_password(self, raw_password):
        self.password = encrypt(raw_password)

    def get_password(self):
        return decrypt(self.password)


class NutanixHost(NetBoxModel):
    """
    Mapping between a Nutanix host (hypervisor node) and a NetBox Device.
    """

    cluster = models.ForeignKey(
        to=NutanixCluster,
        on_delete=models.CASCADE,
        related_name='hosts',
        verbose_name=_('Nutanix endpoint'),
    )
    uuid = models.UUIDField(
        verbose_name=_('Nutanix UUID'),
        unique=True,
    )
    name = models.CharField(
        verbose_name=_('name'),
        max_length=200,
    )
    serial = models.CharField(
        verbose_name=_('serial'),
        max_length=100,
        blank=True,
    )
    ip_address = models.GenericIPAddressField(
        verbose_name=_('IP address'),
        blank=True,
        null=True,
    )
    netbox_device = models.OneToOneField(
        to='dcim.Device',
        on_delete=models.SET_NULL,
        related_name='+',
        blank=True,
        null=True,
        verbose_name=_('NetBox device'),
    )
    last_synced = models.DateTimeField(
        verbose_name=_('last synced'),
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = _('Nutanix host')
        verbose_name_plural = _('Nutanix hosts')
        ordering = ('name',)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('plugins:netbox_nutanix:nutanixhost', args=[self.pk])


class NutanixVirtualMachine(NetBoxModel):
    """
    Mapping between a Nutanix virtual machine and a NetBox VirtualMachine.
    """

    cluster = models.ForeignKey(
        to=NutanixCluster,
        on_delete=models.CASCADE,
        related_name='virtual_machines',
        verbose_name=_('Nutanix endpoint'),
    )
    uuid = models.UUIDField(
        verbose_name=_('Nutanix UUID'),
        unique=True,
    )
    name = models.CharField(
        verbose_name=_('name'),
        max_length=200,
    )
    power_state = models.CharField(
        verbose_name=_('power state'),
        max_length=20,
        blank=True,
    )
    vcpus = models.PositiveIntegerField(
        verbose_name=_('vCPUs'),
        blank=True,
        null=True,
    )
    memory_mb = models.PositiveBigIntegerField(
        verbose_name=_('memory (MB)'),
        blank=True,
        null=True,
    )
    disk_gb = models.PositiveBigIntegerField(
        verbose_name=_('disk (GB)'),
        blank=True,
        null=True,
    )
    host_uuid = models.UUIDField(
        verbose_name=_('host UUID'),
        blank=True,
        null=True,
    )
    netbox_vm = models.OneToOneField(
        to='virtualization.VirtualMachine',
        on_delete=models.SET_NULL,
        related_name='+',
        blank=True,
        null=True,
        verbose_name=_('NetBox virtual machine'),
    )
    last_synced = models.DateTimeField(
        verbose_name=_('last synced'),
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = _('Nutanix virtual machine')
        verbose_name_plural = _('Nutanix virtual machines')
        ordering = ('name',)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('plugins:netbox_nutanix:nutanixvirtualmachine', args=[self.pk])


class NutanixDisk(NetBoxModel):
    """
    Mapping between a Nutanix virtual disk and its parent Nutanix virtual machine.

    NetBox has no native virtual disk model, so each disk is recorded here and
    surfaced beneath the corresponding virtual machine.
    """

    virtual_machine = models.ForeignKey(
        to=NutanixVirtualMachine,
        on_delete=models.CASCADE,
        related_name='disks',
        verbose_name=_('Nutanix virtual machine'),
    )
    uuid = models.UUIDField(
        verbose_name=_('Nutanix UUID'),
        blank=True,
        null=True,
    )
    device_index = models.PositiveIntegerField(
        verbose_name=_('device index'),
        blank=True,
        null=True,
    )
    adapter_type = models.CharField(
        verbose_name=_('adapter type'),
        max_length=50,
        blank=True,
    )
    size_bytes = models.PositiveBigIntegerField(
        verbose_name=_('size (bytes)'),
        blank=True,
        null=True,
    )
    storage_container = models.CharField(
        verbose_name=_('storage container'),
        max_length=255,
        blank=True,
    )

    class Meta:
        verbose_name = _('Nutanix disk')
        verbose_name_plural = _('Nutanix disks')
        ordering = ('virtual_machine', 'device_index', 'pk')

    def __str__(self):
        return f"{self.virtual_machine} disk {self.device_index}"

    def get_absolute_url(self):
        return reverse('plugins:netbox_nutanix:nutanixdisk', args=[self.pk])

    @property
    def size_gb(self):
        if self.size_bytes is None:
            return None
        return int(self.size_bytes / (1024 ** 3))
