from utilities.choices import ChoiceSet


class NutanixDeploymentChoices(ChoiceSet):
    key = 'NutanixCluster.deployment'

    PRISM_CENTRAL = 'pc'
    PRISM_ELEMENT = 'pe'

    CHOICES = [
        (PRISM_CENTRAL, 'Prism Central', 'blue'),
        (PRISM_ELEMENT, 'Prism Element', 'cyan'),
    ]


class NutanixPowerStateChoices(ChoiceSet):
    """Normalized Nutanix power states."""

    ON = 'on'
    OFF = 'off'
    PAUSED = 'paused'
    UNKNOWN = 'unknown'

    CHOICES = [
        (ON, 'On', 'green'),
        (OFF, 'Off', 'gray'),
        (PAUSED, 'Paused', 'orange'),
        (UNKNOWN, 'Unknown', 'red'),
    ]
