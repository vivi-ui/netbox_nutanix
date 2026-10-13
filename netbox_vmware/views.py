from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views import View

from netbox.object_actions import AddObject, BulkDelete, BulkEdit, BulkExport, BulkImport, DeleteObject
from netbox.views import generic
from utilities.views import register_model_view

from . import filtersets, forms, models, tables
from .jobs import VMwareSyncJob


#
# Endpoints
#

@register_model_view(models.VMwareEndpoint)
class VMwareEndpointView(generic.ObjectView):
    queryset = models.VMwareEndpoint.objects.all()

    def get_extra_context(self, request, instance):
        return {
            'hosts_table': tables.VMwareHostTable(instance.hosts.all(), orderable=False),
            'vms_table': tables.VMwareVirtualMachineTable(
                instance.virtual_machines.all(), orderable=False
            ),
        }


class VMwareEndpointListView(generic.ObjectListView):
    queryset = models.VMwareEndpoint.objects.all()
    table = tables.VMwareEndpointTable
    filterset = filtersets.VMwareEndpointFilterSet
    filterset_form = forms.VMwareEndpointFilterForm
    actions = (AddObject, BulkImport, BulkExport, BulkEdit, BulkDelete)


@register_model_view(models.VMwareEndpoint, 'edit')
class VMwareEndpointEditView(generic.ObjectEditView):
    queryset = models.VMwareEndpoint.objects.all()
    form = forms.VMwareEndpointForm


@register_model_view(models.VMwareEndpoint, 'delete')
class VMwareEndpointDeleteView(generic.ObjectDeleteView):
    queryset = models.VMwareEndpoint.objects.all()


class VMwareEndpointBulkImportView(generic.BulkImportView):
    queryset = models.VMwareEndpoint.objects.all()
    model_form = forms.VMwareEndpointImportForm


class VMwareEndpointBulkEditView(generic.BulkEditView):
    queryset = models.VMwareEndpoint.objects.all()
    filterset = filtersets.VMwareEndpointFilterSet
    table = tables.VMwareEndpointTable
    form = forms.VMwareEndpointBulkEditForm


class VMwareEndpointBulkDeleteView(generic.BulkDeleteView):
    queryset = models.VMwareEndpoint.objects.all()
    filterset = filtersets.VMwareEndpointFilterSet
    table = tables.VMwareEndpointTable


class VMwareEndpointSyncView(View):
    """
    Enqueue a background synchronization job for a single endpoint.
    """

    def post(self, request, pk):
        endpoint = get_object_or_404(
            models.VMwareEndpoint.objects.restrict(request.user, 'change'), pk=pk
        )

        sync_hosts = request.POST.get('sync_hosts', 'true') != 'false'
        sync_vms = request.POST.get('sync_vms', 'true') != 'false'

        VMwareSyncJob.enqueue(
            instance=endpoint,
            user=request.user,
            name=f"VMware sync: {endpoint}",
            cluster_pk=endpoint.pk,
            sync_hosts=sync_hosts,
            sync_vms=sync_vms,
        )

        messages.success(request, f"Synchronization job enqueued for '{endpoint}'.")
        return redirect(endpoint.get_absolute_url())


#
# Hosts
#

class VMwareHostListView(generic.ObjectListView):
    queryset = models.VMwareHost.objects.all()
    table = tables.VMwareHostTable
    filterset = filtersets.VMwareHostFilterSet
    filterset_form = forms.VMwareHostFilterForm
    actions = (BulkExport, BulkDelete)


@register_model_view(models.VMwareHost)
class VMwareHostView(generic.ObjectView):
    queryset = models.VMwareHost.objects.all()
    actions = (DeleteObject,)


@register_model_view(models.VMwareHost, 'delete')
class VMwareHostDeleteView(generic.ObjectDeleteView):
    queryset = models.VMwareHost.objects.all()


class VMwareHostBulkDeleteView(generic.BulkDeleteView):
    queryset = models.VMwareHost.objects.all()
    filterset = filtersets.VMwareHostFilterSet
    table = tables.VMwareHostTable


#
# Virtual machines
#

class VMwareVMListView(generic.ObjectListView):
    queryset = models.VMwareVirtualMachine.objects.all()
    table = tables.VMwareVirtualMachineTable
    filterset = filtersets.VMwareVirtualMachineFilterSet
    filterset_form = forms.VMwareVirtualMachineFilterForm
    actions = (BulkExport, BulkDelete)


@register_model_view(models.VMwareVirtualMachine)
class VMwareVMView(generic.ObjectView):
    queryset = models.VMwareVirtualMachine.objects.all()
    actions = (DeleteObject,)

    def get_extra_context(self, request, instance):
        return {
            'disks_table': tables.VMwareDiskTable(instance.disks.all(), orderable=False),
        }


@register_model_view(models.VMwareVirtualMachine, 'delete')
class VMwareVMDeleteView(generic.ObjectDeleteView):
    queryset = models.VMwareVirtualMachine.objects.all()


class VMwareVMBulkDeleteView(generic.BulkDeleteView):
    queryset = models.VMwareVirtualMachine.objects.all()
    filterset = filtersets.VMwareVirtualMachineFilterSet
    table = tables.VMwareVirtualMachineTable


#
# Disks
#

class VMwareDiskListView(generic.ObjectListView):
    queryset = models.VMwareDisk.objects.all()
    table = tables.VMwareDiskTable
    filterset = filtersets.VMwareDiskFilterSet
    filterset_form = forms.VMwareDiskFilterForm
    actions = (BulkExport, BulkDelete)


@register_model_view(models.VMwareDisk)
class VMwareDiskView(generic.ObjectView):
    queryset = models.VMwareDisk.objects.all()
    actions = (DeleteObject,)


@register_model_view(models.VMwareDisk, 'delete')
class VMwareDiskDeleteView(generic.ObjectDeleteView):
    queryset = models.VMwareDisk.objects.all()


class VMwareDiskBulkDeleteView(generic.BulkDeleteView):
    queryset = models.VMwareDisk.objects.all()
    filterset = filtersets.VMwareDiskFilterSet
    table = tables.VMwareDiskTable
