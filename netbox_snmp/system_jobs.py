"""
Optional recurring synchronization.

This module is imported from ``SnmpSyncConfig.ready()`` only when the
``sync_interval`` plugin setting is configured to a non-zero value, which keeps
the periodic system job from being registered (and therefore scheduled) unless
an administrator explicitly opts in.
"""

from netbox.jobs import system_job
from netbox.plugins import get_plugin_config

from .jobs import SnmpSyncJob
from .sync import run_sync_for_all


def _get_interval():
    try:
        return int(get_plugin_config('netbox_snmp', 'sync_interval') or 0)
    except Exception:
        return 0


@system_job(_get_interval())
class SnmpPeriodicSyncJob(SnmpSyncJob):
    """
    Recurring job which synchronizes every enabled SNMP endpoint.
    """

    class Meta:
        name = 'SNMP Periodic Sync'

    def run(self, *args, **kwargs):
        results = run_sync_for_all(log=self.logger.info)
        for endpoint_pk, result in results.items():
            self.logger.info(f"Endpoint {endpoint_pk}: {result.summary()}")
