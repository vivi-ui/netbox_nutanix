from netbox.jobs import JobRunner

from .exceptions import NutanixError
from .models import NutanixCluster
from .sync import run_sync


class NutanixSyncJob(JobRunner):
    """
    Background job which synchronizes a single Nutanix endpoint into NetBox.
    """

    class Meta:
        name = 'Nutanix Sync'

    def run(self, cluster_pk, sync_hosts=True, sync_vms=True, **kwargs):
        endpoint = NutanixCluster.objects.get(pk=cluster_pk)
        self.logger.info(
            f"Starting Nutanix sync for endpoint '{endpoint}' "
            f"(hosts={sync_hosts}, vms={sync_vms})"
        )
        try:
            result = run_sync(
                endpoint,
                log=self.logger.info,
                sync_hosts=sync_hosts,
                sync_vms=sync_vms,
            )
        except NutanixError as e:
            self.logger.error(f"Nutanix sync failed for endpoint '{endpoint}': {e}")
            raise

        self.logger.info(f"Nutanix sync finished for endpoint '{endpoint}': {result.summary()}")
        return result.summary()
