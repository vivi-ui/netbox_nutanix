from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox.models import NetBoxModel
from netbox.models.features import JobsMixin

from .choices import (
    SnmpAuthProtocolChoices,
    SnmpPrivProtocolChoices,
    SnmpSecurityLevelChoices,
    SnmpVersionChoices,
)
from .crypto import decrypt, encrypt


class SnmpEndpoint(JobsMixin, NetBoxModel):
    """
    Connection and synchronization configuration for a set of SNMP devices.

    An endpoint holds the SNMP credentials (v2c community or v3 USM user) shared
    by every device reached through it together with the NetBox objects that
    newly discovered devices should be associated with.
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

    snmp_version = models.CharField(
        verbose_name=_('SNMP version'),
        max_length=10,
        choices=SnmpVersionChoices,
        default=SnmpVersionChoices.V2C,
    )
    community = models.CharField(
        verbose_name=_('community'),
        max_length=500,
        blank=True,
        help_text=_("SNMPv2c community string. Stored encrypted."),
    )
    security_username = models.CharField(
        verbose_name=_('security username'),
        max_length=150,
        blank=True,
        help_text=_("SNMPv3 USM username."),
    )
    security_level = models.CharField(
        verbose_name=_('security level'),
        max_length=20,
        choices=SnmpSecurityLevelChoices,
        default=SnmpSecurityLevelChoices.AUTH_PRIV,
    )
    auth_protocol = models.CharField(
        verbose_name=_('authentication protocol'),
        max_length=20,
        choices=SnmpAuthProtocolChoices,
        default=SnmpAuthProtocolChoices.SHA,
    )
    auth_key = models.CharField(
        verbose_name=_('authentication key'),
        max_length=500,
        blank=True,
        help_text=_("SNMPv3 authentication passphrase. Stored encrypted."),
    )
    priv_protocol = models.CharField(
        verbose_name=_('privacy protocol'),
        max_length=20,
        choices=SnmpPrivProtocolChoices,
        default=SnmpPrivProtocolChoices.AES128,
    )
    priv_key = models.CharField(
        verbose_name=_('privacy key'),
        max_length=500,
        blank=True,
        help_text=_("SNMPv3 privacy passphrase. Stored encrypted."),
    )
    port = models.PositiveIntegerField(
        verbose_name=_('port'),
        default=161,
        help_text=_("Destination UDP port."),
    )
    timeout = models.PositiveIntegerField(
        verbose_name=_('timeout'),
        default=5,
        help_text=_("Request timeout in seconds."),
    )
    retries = models.PositiveIntegerField(
        verbose_name=_('retries'),
        default=2,
        help_text=_("Number of retries per request."),
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
        help_text=_("Role assigned to discovered devices. Defaults to 'Network' when unset."),
    )
    manufacturer = models.ForeignKey(
        to='dcim.Manufacturer',
        on_delete=models.SET_NULL,
        related_name='+',
        blank=True,
        null=True,
        verbose_name=_('manufacturer'),
        help_text=_("Manufacturer assigned to discovered device types. Defaults to 'Generic'."),
    )
    device_type = models.ForeignKey(
        to='dcim.DeviceType',
        on_delete=models.SET_NULL,
        related_name='+',
        blank=True,
        null=True,
        verbose_name=_('device type'),
        help_text=_("Device type assigned to all discovered devices. Derived from sysObjectID when unset."),
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
        help_text=_("Delete NetBox objects no longer present on the discovered devices."),
    )
    discover_neighbors = models.BooleanField(
        verbose_name=_('discover neighbors'),
        default=True,
        help_text=_("Follow LLDP/CDP neighbors to discover adjacent switches."),
    )
    create_cables = models.BooleanField(
        verbose_name=_('create cables'),
        default=False,
        help_text=_(
            "Create a cable between each local interface and its LLDP/CDP "
            "neighbor once both devices have been discovered."
        ),
    )
    collect_vlans = models.BooleanField(
        verbose_name=_('collect VLANs'),
        default=False,
        help_text=_(
            "Read the Q-BRIDGE-MIB VLAN table and assign the untagged/tagged "
            "VLANs to each interface."
        ),
    )
    infer_prefixes = models.BooleanField(
        verbose_name=_('infer prefixes'),
        default=False,
        help_text=_(
            "Derive IP prefixes from layer-3 SVI interfaces and link them to "
            "the matching VLAN."
        ),
    )
    collect_arp = models.BooleanField(
        verbose_name=_('collect ARP'),
        default=False,
        help_text=_("Read the ARP table and register the discovered IP addresses."),
    )
    collect_fdb = models.BooleanField(
        verbose_name=_('collect forwarding table'),
        default=False,
        help_text=_(
            "Read the BRIDGE-MIB forwarding table to resolve ARP entries to "
            "the correct interface."
        ),
    )
    max_arp_entries = models.PositiveIntegerField(
        verbose_name=_('maximum ARP entries'),
        default=1000,
        help_text=_("Safety limit on the number of ARP entries processed per device."),
    )
    collect_modules = models.BooleanField(
        verbose_name=_('collect modules'),
        default=False,
        help_text=_(
            "Read the ENTITY-MIB physical table and reconcile the chassis "
            "module bays and their installed modules (line cards, power "
            "supplies and fans)."
        ),
    )
    max_depth = models.PositiveIntegerField(
        verbose_name=_('maximum discovery depth'),
        default=1,
        help_text=_("How many hops of neighbors to follow (0 = only the configured targets)."),
    )
    max_devices = models.PositiveIntegerField(
        verbose_name=_('maximum devices'),
        default=256,
        help_text=_("Safety limit on the number of devices visited during a single sync run."),
    )

    class Meta:
        verbose_name = _('SNMP endpoint')
        verbose_name_plural = _('SNMP endpoints')
        ordering = ('name',)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('plugins:netbox_snmp:snmpendpoint', args=[self.pk])

    def set_community(self, raw):
        self.community = encrypt(raw)

    def get_community(self):
        return decrypt(self.community)

    def set_auth_key(self, raw):
        self.auth_key = encrypt(raw)

    def get_auth_key(self):
        return decrypt(self.auth_key)

    def set_priv_key(self, raw):
        self.priv_key = encrypt(raw)

    def get_priv_key(self):
        return decrypt(self.priv_key)


class SnmpTarget(NetBoxModel):
    """
    A single address (host or CIDR) that should be polled by an endpoint.
    """

    endpoint = models.ForeignKey(
        to=SnmpEndpoint,
        on_delete=models.CASCADE,
        related_name='targets',
        verbose_name=_('SNMP endpoint'),
    )
    address = models.CharField(
        verbose_name=_('address'),
        max_length=64,
        help_text=_("IPv4/IPv6 address or network in CIDR notation, e.g. 10.0.0.1 or 10.0.0.0/24."),
    )
    enabled = models.BooleanField(
        verbose_name=_('enabled'),
        default=True,
    )
    description = models.CharField(
        verbose_name=_('description'),
        max_length=200,
        blank=True,
    )

    class Meta:
        verbose_name = _('SNMP target')
        verbose_name_plural = _('SNMP targets')
        ordering = ('endpoint', 'address')
        constraints = (
            models.UniqueConstraint(
                fields=('endpoint', 'address'),
                name='netbox_snmp_target_unique_endpoint_address',
            ),
        )

    def __str__(self):
        return self.address

    def get_absolute_url(self):
        return reverse('plugins:netbox_snmp:snmptarget', args=[self.pk])


class SnmpDevice(NetBoxModel):
    """
    Mapping between a discovered SNMP device and a NetBox Device.
    """

    endpoint = models.ForeignKey(
        to=SnmpEndpoint,
        on_delete=models.CASCADE,
        related_name='devices',
        verbose_name=_('SNMP endpoint'),
    )
    address = models.GenericIPAddressField(
        verbose_name=_('address'),
        help_text=_("Management address used to reach the device."),
    )
    sys_name = models.CharField(
        verbose_name=_('system name'),
        max_length=255,
        blank=True,
    )
    sys_object_id = models.CharField(
        verbose_name=_('system object ID'),
        max_length=255,
        blank=True,
    )
    sys_descr = models.TextField(
        verbose_name=_('system description'),
        blank=True,
    )
    sys_location = models.CharField(
        verbose_name=_('system location'),
        max_length=255,
        blank=True,
    )
    sys_contact = models.CharField(
        verbose_name=_('system contact'),
        max_length=255,
        blank=True,
    )
    serial = models.CharField(
        verbose_name=_('serial'),
        max_length=100,
        blank=True,
    )
    uptime = models.PositiveBigIntegerField(
        verbose_name=_('uptime (seconds)'),
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
        verbose_name = _('SNMP device')
        verbose_name_plural = _('SNMP devices')
        ordering = ('sys_name', 'address')
        constraints = (
            models.UniqueConstraint(
                fields=('endpoint', 'address'),
                name='netbox_snmp_device_unique_endpoint_address',
            ),
        )

    def __str__(self):
        return self.sys_name or str(self.address)

    def get_absolute_url(self):
        return reverse('plugins:netbox_snmp:snmpdevice', args=[self.pk])
