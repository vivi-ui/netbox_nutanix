from core.models import Job
from netbox.jobs import JobRunner

from .exceptions import SnmpError
from .models import SnmpEndpoint
from .sync import run_sync


class SnmpSyncJob(JobRunner):
    """
    Background job which discovers a single SNMP endpoint into NetBox.
    """

    class Meta:
        name = 'SNMP Sync'

    def run(self, endpoint_pk, **kwargs):
        endpoint = SnmpEndpoint.objects.get(pk=endpoint_pk)
        self.logger.info(f"Starting SNMP sync for endpoint '{endpoint}'")

        def cancel_check():
            data = Job.objects.filter(pk=self.job.pk).values_list('data', flat=True).first()
            return bool(data and data.get('stop_requested'))

        try:
            result = run_sync(endpoint, log=self.logger.info, cancel_check=cancel_check)
        except SnmpError as e:
            self.logger.error(f"SNMP sync failed for endpoint '{endpoint}': {e}")
            raise

        if result.cancelled:
            self.logger.warning(f"SNMP sync for endpoint '{endpoint}' was cancelled")
        else:
            self.logger.info(f"SNMP sync finished for endpoint '{endpoint}': {result.summary()}")
        return result.summary()
