import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.choices import JobStatusChoices
from core.models import Job, ObjectType
from dcim.models import Site

from netbox_snmp.models import SnmpEndpoint


class CancelViewTestCase(TestCase):
    def setUp(self):
        self.site = Site.objects.create(name='View Site', slug='view-site')
        self.endpoint = SnmpEndpoint.objects.create(name='snmp-view', site=self.site)
        self.user = get_user_model().objects.create_superuser('admin', 'a@b.c', 'pw')
        self.client.force_login(self.user)

    def _running_job(self):
        return Job.objects.create(
            name=f"SNMP sync: {self.endpoint}",
            status=JobStatusChoices.STATUS_RUNNING,
            job_id=uuid.uuid4(),
            object_type=ObjectType.objects.get_for_model(SnmpEndpoint),
            object_id=self.endpoint.pk,
        )

    def test_cancel_sets_stop_flag(self):
        job = self._running_job()
        url = reverse('plugins:netbox_snmp:snmpendpoint_cancel', args=[self.endpoint.pk])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        job.refresh_from_db()
        self.assertTrue(job.data.get('stop_requested'))

    def test_cancel_without_running_job_warns(self):
        url = reverse('plugins:netbox_snmp:snmpendpoint_cancel', args=[self.endpoint.pk])
        response = self.client.post(url, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No running discovery job')
