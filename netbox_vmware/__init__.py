from netbox.plugins import PluginConfig, get_plugin_config


class VMwareSyncConfig(PluginConfig):
    name = 'netbox_vmware'
    verbose_name = 'VMware Sync'
    description = 'Synchronize VMware ESXi hosts and virtual machines into NetBox'
    version = '0.1.0'
    author = 'MonkeyCode'
    author_email = 'support@monkeycode-ai.com'
    base_url = 'vmware'
    min_version = '4.4.0'
    max_version = '4.6.99'
    default_settings = {
        # 0 disables the periodic background sync
        'sync_interval': 0,
        # Default connection timeout (seconds) used when an endpoint does not override it
        'request_timeout': 30,
        # Verify TLS certificates when talking to the VMware API by default
        'verify_ssl': True,
    }

    def ready(self):
        super().ready()

        # Register the optional periodic sync job only when a non-zero interval is configured.
        try:
            interval = int(get_plugin_config('netbox_vmware', 'sync_interval') or 0)
        except Exception:
            interval = 0

        if interval > 0:
            from . import system_jobs  # noqa: F401


config = VMwareSyncConfig
