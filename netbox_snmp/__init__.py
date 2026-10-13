from netbox.plugins import PluginConfig, get_plugin_config


class SnmpSyncConfig(PluginConfig):
    name = 'netbox_snmp'
    verbose_name = 'SNMP Network Discovery'
    description = 'Discover network devices and their interfaces over SNMP (v2c/v3)'
    version = '0.1.0'
    author = 'MonkeyCode'
    author_email = 'support@monkeycode-ai.com'
    base_url = 'snmp'
    min_version = '4.4.0'
    max_version = '4.6.99'
    default_settings = {
        # 0 disables the periodic background sync
        'sync_interval': 0,
        # Default SNMP timeouts (seconds) used when an endpoint does not override them
        'request_timeout': 5,
        'request_retries': 2,
        # Upper bound on the number of devices visited during a single sync run
        'max_devices': 256,
        # Follow LLDP/CDP neighbors by default when an endpoint does not override it
        'discover_neighbors': True,
        # Maximum neighbor discovery depth (0 = only the configured targets)
        'max_depth': 1,
    }

    def ready(self):
        super().ready()

        # Register the optional periodic sync job only when a non-zero interval is configured.
        try:
            interval = int(get_plugin_config('netbox_snmp', 'sync_interval') or 0)
        except Exception:
            interval = 0

        if interval > 0:
            from . import system_jobs  # noqa: F401


config = SnmpSyncConfig
