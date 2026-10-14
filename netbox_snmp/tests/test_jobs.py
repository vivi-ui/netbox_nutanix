import uuid
from dataclasses import asdict

from django.test import TestCase

from core.choices import JobStatusChoices
from core.dataclasses import JobLogEntry
from core.models import Job, ObjectType
from dcim.models import Site

from netbox_snmp.jobs import SnmpSyncJob
from netbox_snmp.models import SnmpEndpoint


class SnmpSyncJobLogTestCase(TestCase):
    def setUp(self):
        site = Site.objects.create(name='Job Site', slug='job-site')
        self.endpoint = SnmpEndpoint.objects.create(name='snmp-job', site=site)
        self.job = Job.objects.create(
            name='SNMP sync',
            status=JobStatusChoices.STATUS_RUNNING,
            job_id=uuid.uuid4(),
            object_type=ObjectType.objects.get_for_model(SnmpEndpoint),
            object_id=self.endpoint.pk,
        )

    def test_flush_log_persists_entries(self):
        runner = SnmpSyncJob(self.job)
        runner.logger.info('probing candidates')
        runner.logger.info('device synced')
        runner._flush_log()

        job = Job.objects.get(pk=self.job.pk)
        messages = [entry['message'] for entry in job.log_entries]
        self.assertIn('probing candidates', messages)
        self.assertIn('device synced', messages)

    def test_flush_log_preserves_concurrent_stop_flag(self):
        # Simulate the cancel view writing stop_requested to the DB while the
        # in-memory job still holds stale data.
        Job.objects.filter(pk=self.job.pk).update(data={'stop_requested': True})

        runner = SnmpSyncJob(self.job)
        runner._flush_log()

        job = Job.objects.get(pk=self.job.pk)
        self.assertTrue(job.data.get('stop_requested'))

    def test_log_entries_are_job_log_entries(self):
        runner = SnmpSyncJob(self.job)
        entry = asdict(JobLogEntry('info', 'hello'))
        self.job.log_entries.append(entry)
        runner._flush_log()

        job = Job.objects.get(pk=self.job.pk)
        self.assertEqual(job.log_entries[-1]['message'], 'hello')
