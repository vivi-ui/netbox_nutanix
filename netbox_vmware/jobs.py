from netbox.jobs import JobRunner

from .exceptions import VMwareError
from .models import VMwareEndpoint
from .sync import run_sync


class VMwareSyncJob(JobRunner):
    """
    Background job which synchronizes a single VMware endpoint into NetBox.
    """

    class Meta:
        name = 'VMware Sync'

    def run(self, cluster_pk, sync_hosts=True, sync_vms=True, **kwargs):
        endpoint = VMwareEndpoint.objects.get(pk=cluster_pk)
        self.logger.info(
            f"Starting VMware sync for endpoint '{endpoint}' "
            f"(hosts={sync_hosts}, vms={sync_vms})"
        )
        try:
            result = run_sync(
                endpoint,
                log=self.logger.info,
                sync_hosts=sync_hosts,
                sync_vms=sync_vms,
            )
        except VMwareError as e:
            self.logger.error(f"VMware sync failed for endpoint '{endpoint}': {e}")
            raise

        self.logger.info(f"VMware sync finished for endpoint '{endpoint}': {result.summary()}")
        return result.summary()
