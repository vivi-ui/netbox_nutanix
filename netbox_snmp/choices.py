from utilities.choices import ChoiceSet


class SnmpVersionChoices(ChoiceSet):
    key = 'SnmpEndpoint.snmp_version'

    V2C = '2c'
    V3 = '3'

    CHOICES = [
        (V2C, 'SNMPv2c', 'blue'),
        (V3, 'SNMPv3', 'purple'),
    ]


class SnmpSecurityLevelChoices(ChoiceSet):
    key = 'SnmpEndpoint.security_level'

    NO_AUTH_NO_PRIV = 'noauthnopriv'
    AUTH_NO_PRIV = 'authnopriv'
    AUTH_PRIV = 'authpriv'

    CHOICES = [
        (NO_AUTH_NO_PRIV, 'noAuthNoPriv', 'gray'),
        (AUTH_NO_PRIV, 'authNoPriv', 'blue'),
        (AUTH_PRIV, 'authPriv', 'green'),
    ]


class SnmpAuthProtocolChoices(ChoiceSet):
    key = 'SnmpEndpoint.auth_protocol'

    MD5 = 'md5'
    SHA = 'sha'
    SHA224 = 'sha224'
    SHA256 = 'sha256'
    SHA384 = 'sha384'
    SHA512 = 'sha512'

    CHOICES = [
        (MD5, 'MD5', 'red'),
        (SHA, 'SHA', 'orange'),
        (SHA224, 'SHA-224', 'yellow'),
        (SHA256, 'SHA-256', 'green'),
        (SHA384, 'SHA-384', 'blue'),
        (SHA512, 'SHA-512', 'purple'),
    ]


class SnmpPrivProtocolChoices(ChoiceSet):
    key = 'SnmpEndpoint.priv_protocol'

    DES = 'des'
    TRIPLE_DES = '3des'
    AES128 = 'aes128'
    AES192 = 'aes192'
    AES256 = 'aes256'

    CHOICES = [
        (DES, 'DES', 'red'),
        (TRIPLE_DES, '3DES', 'orange'),
        (AES128, 'AES-128', 'green'),
        (AES192, 'AES-192', 'blue'),
        (AES256, 'AES-256', 'purple'),
    ]
