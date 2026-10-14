import time

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

    # NetBox only persists a Job's log entries on start()/terminate(), so a long
    # run appears to hang in the web UI until it finishes. Flush the accumulated
    # entries at most this often (seconds) so the progress can be followed live.
    LOG_FLUSH_INTERVAL = 2.0

    def run(self, endpoint_pk, **kwargs):
        endpoint = SnmpEndpoint.objects.get(pk=endpoint_pk)
        last_flush = [0.0]

        def log(message):
            self.logger.info(message)
            now = time.monotonic()
            if now - last_flush[0] >= self.LOG_FLUSH_INTERVAL:
                self._flush_log()
                last_flush[0] = now

        def cancel_check():
            data = Job.objects.filter(pk=self.job.pk).values_list('data', flat=True).first()
            return bool(data and data.get('stop_requested'))

        try:
            result = run_sync(endpoint, log=log, cancel_check=cancel_check)
        except SnmpError as e:
            log(f"SNMP sync failed for endpoint '{endpoint}': {e}")
            self._flush_log()
            raise

        if result.cancelled:
            log(f"SNMP sync for endpoint '{endpoint}' was cancelled")
        self._flush_log()
        return result.summary()

    def _flush_log(self):
        """
        Persist the in-memory log entries without touching any other field.

        A targeted ``update()`` is used (rather than ``save()``) so a concurrent
        ``stop_requested`` flag written to ``data`` by the cancel view is not
        clobbered.
        """
        Job.objects.filter(pk=self.job.pk).update(log_entries=self.job.log_entries)
