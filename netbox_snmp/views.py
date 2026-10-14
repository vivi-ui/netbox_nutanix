from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from core.choices import JobStatusChoices
from core.models import Job
from netbox.object_actions import AddObject, BulkDelete, BulkEdit, BulkExport, BulkImport, DeleteObject
from netbox.views import generic
from utilities.views import register_model_view

from . import filtersets, forms, models, tables
from .jobs import SnmpSyncJob
from .utils import parse_target_addresses


#
# Endpoints
#

@register_model_view(models.SnmpEndpoint)
class SnmpEndpointView(generic.ObjectView):
    queryset = models.SnmpEndpoint.objects.all()

    def get_extra_context(self, request, instance):
        object_type = ContentType.objects.get_for_model(models.SnmpEndpoint)
        latest_job = Job.objects.filter(
            object_type=object_type,
            object_id=instance.pk,
        ).order_by('-created').first()
        job_logs = list(latest_job.log_entries or [])[-12:] if latest_job else []
        return {
            'targets_table': tables.SnmpTargetTable(
                instance.targets.all(), orderable=False
            ),
            'devices_table': tables.SnmpDeviceTable(
                instance.devices.all(), orderable=False
            ),
            'latest_job': latest_job,
            'job_logs': job_logs,
            'job_running': bool(
                latest_job and latest_job.status in JobStatusChoices.ENQUEUED_STATE_CHOICES
            ),
        }


class SnmpEndpointListView(generic.ObjectListView):
    queryset = models.SnmpEndpoint.objects.all()
    table = tables.SnmpEndpointTable
    filterset = filtersets.SnmpEndpointFilterSet
    filterset_form = forms.SnmpEndpointFilterForm
    actions = (AddObject, BulkImport, BulkExport, BulkEdit, BulkDelete)


@register_model_view(models.SnmpEndpoint, 'edit')
class SnmpEndpointEditView(generic.ObjectEditView):
    queryset = models.SnmpEndpoint.objects.all()
    form = forms.SnmpEndpointForm


@register_model_view(models.SnmpEndpoint, 'delete')
class SnmpEndpointDeleteView(generic.ObjectDeleteView):
    queryset = models.SnmpEndpoint.objects.all()


class SnmpEndpointBulkImportView(generic.BulkImportView):
    queryset = models.SnmpEndpoint.objects.all()
    model_form = forms.SnmpEndpointImportForm


class SnmpEndpointBulkEditView(generic.BulkEditView):
    queryset = models.SnmpEndpoint.objects.all()
    filterset = filtersets.SnmpEndpointFilterSet
    table = tables.SnmpEndpointTable
    form = forms.SnmpEndpointBulkEditForm


class SnmpEndpointBulkDeleteView(generic.BulkDeleteView):
    queryset = models.SnmpEndpoint.objects.all()
    filterset = filtersets.SnmpEndpointFilterSet
    table = tables.SnmpEndpointTable


class SnmpEndpointSyncView(View):
    """
    Enqueue a background discovery job for a single endpoint.
    """

    def post(self, request, pk):
        endpoint = get_object_or_404(
            models.SnmpEndpoint.objects.restrict(request.user, 'change'), pk=pk
        )
        SnmpSyncJob.enqueue(
            instance=endpoint,
            user=request.user,
            name=f"SNMP sync: {endpoint}",
            endpoint_pk=endpoint.pk,
        )
        messages.success(request, f"Discovery job enqueued for '{endpoint}'.")
        return redirect(endpoint.get_absolute_url())


class SnmpEndpointCancelView(View):
    """
    Request a graceful stop of the endpoint's running discovery job(s).

    A flag is written to each running job's ``data``; the synchronizer checks it
    between targets and stops at the next safe point, so the job still finishes
    cleanly (instead of being killed mid-write).
    """

    def post(self, request, pk):
        endpoint = get_object_or_404(
            models.SnmpEndpoint.objects.restrict(request.user, 'change'), pk=pk
        )
        object_type = ContentType.objects.get_for_model(models.SnmpEndpoint)
        jobs = Job.objects.filter(
            object_type=object_type,
            object_id=endpoint.pk,
            status__in=JobStatusChoices.ENQUEUED_STATE_CHOICES,
        )

        requested = 0
        for job in jobs:
            data = dict(job.data or {})
            if data.get('stop_requested'):
                continue
            data['stop_requested'] = True
            job.data = data
            job.save(update_fields=['data'])
            requested += 1

        if requested:
            messages.success(
                request, f"Requested cancellation of {requested} job(s) for '{endpoint}'."
            )
        else:
            messages.warning(request, f"No running discovery job found for '{endpoint}'.")
        return redirect(endpoint.get_absolute_url())


#
# Targets
#

class SnmpTargetMultiAddView(LoginRequiredMixin, View):
    """
    Create one SNMP target per address/network supplied in a single form.
    """

    template_name = 'netbox_snmp/snmptarget_multi_add.html'

    def _check_permission(self, request):
        if not request.user.has_perm('netbox_snmp.add_snmptarget'):
            raise PermissionDenied

    def get(self, request):
        self._check_permission(request)
        initial = {'enabled': True}
        endpoint = request.GET.get('endpoint')
        if endpoint:
            initial['endpoint'] = endpoint
        form = forms.SnmpTargetMultiAddForm(initial=initial)
        return render(request, self.template_name, {
            'form': form,
            'endpoint': endpoint,
        })

    def post(self, request):
        self._check_permission(request)
        form = forms.SnmpTargetMultiAddForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form})

        endpoint = form.cleaned_data['endpoint']
        enabled = form.cleaned_data['enabled']
        description = form.cleaned_data['description'] or ''
        valid, invalid = parse_target_addresses(form.cleaned_data['addresses'])

        created = 0
        for address in valid:
            _, was_created = models.SnmpTarget.objects.get_or_create(
                endpoint=endpoint,
                address=address,
                defaults={'enabled': enabled, 'description': description},
            )
            if was_created:
                created += 1

        if created:
            messages.success(request, f"Added {created} target(s) to '{endpoint}'.")
        skipped = len(valid) - created
        if skipped:
            messages.info(request, f"{skipped} target(s) already existed and were skipped.")
        if invalid:
            messages.warning(request, "Ignored invalid entries: " + ', '.join(invalid))
        if not valid:
            messages.warning(request, "No valid addresses were supplied.")

        return redirect(endpoint.get_absolute_url())


@register_model_view(models.SnmpTarget)
class SnmpTargetView(generic.ObjectView):
    queryset = models.SnmpTarget.objects.all()


class SnmpTargetListView(generic.ObjectListView):
    queryset = models.SnmpTarget.objects.all()
    table = tables.SnmpTargetTable
    filterset = filtersets.SnmpTargetFilterSet
    filterset_form = forms.SnmpTargetFilterForm
    actions = (AddObject, BulkImport, BulkExport, BulkEdit, BulkDelete)


@register_model_view(models.SnmpTarget, 'edit')
class SnmpTargetEditView(generic.ObjectEditView):
    queryset = models.SnmpTarget.objects.all()
    form = forms.SnmpTargetForm


@register_model_view(models.SnmpTarget, 'delete')
class SnmpTargetDeleteView(generic.ObjectDeleteView):
    queryset = models.SnmpTarget.objects.all()


class SnmpTargetBulkImportView(generic.BulkImportView):
    queryset = models.SnmpTarget.objects.all()
    model_form = forms.SnmpTargetImportForm


class SnmpTargetBulkEditView(generic.BulkEditView):
    queryset = models.SnmpTarget.objects.all()
    filterset = filtersets.SnmpTargetFilterSet
    table = tables.SnmpTargetTable
    form = forms.SnmpTargetBulkEditForm


class SnmpTargetBulkDeleteView(generic.BulkDeleteView):
    queryset = models.SnmpTarget.objects.all()
    filterset = filtersets.SnmpTargetFilterSet
    table = tables.SnmpTargetTable


#
# Devices
#

class SnmpDeviceListView(generic.ObjectListView):
    queryset = models.SnmpDevice.objects.all()
    table = tables.SnmpDeviceTable
    filterset = filtersets.SnmpDeviceFilterSet
    filterset_form = forms.SnmpDeviceFilterForm
    actions = (BulkExport, BulkDelete)


@register_model_view(models.SnmpDevice)
class SnmpDeviceView(generic.ObjectView):
    queryset = models.SnmpDevice.objects.all()
    actions = (DeleteObject,)


@register_model_view(models.SnmpDevice, 'delete')
class SnmpDeviceDeleteView(generic.ObjectDeleteView):
    queryset = models.SnmpDevice.objects.all()


class SnmpDeviceBulkDeleteView(generic.BulkDeleteView):
    queryset = models.SnmpDevice.objects.all()
    filterset = filtersets.SnmpDeviceFilterSet
    table = tables.SnmpDeviceTable
