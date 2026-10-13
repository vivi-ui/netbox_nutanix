from utilities.choices import ChoiceSet


class VMwareDeploymentChoices(ChoiceSet):
    key = 'VMwareEndpoint.deployment'

    VCENTER = 'vcenter'
    ESXI = 'esxi'

    CHOICES = [
        (VCENTER, 'vCenter', 'blue'),
        (ESXI, 'ESXi', 'cyan'),
    ]


class VMwarePowerStateChoices(ChoiceSet):
    """Normalized VMware power states."""

    ON = 'on'
    OFF = 'off'
    SUSPENDED = 'suspended'
    UNKNOWN = 'unknown'

    CHOICES = [
        (ON, 'On', 'green'),
        (OFF, 'Off', 'gray'),
        (SUSPENDED, 'Suspended', 'orange'),
        (UNKNOWN, 'Unknown', 'red'),
    ]
