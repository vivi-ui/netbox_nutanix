from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views import View

from netbox.object_actions import AddObject, BulkDelete, BulkEdit, BulkExport, BulkImport, DeleteObject
from netbox.views import generic
from utilities.views import register_model_view

from . import filtersets, forms, models, tables
from .jobs import NutanixSyncJob


#
# Endpoints
#

@register_model_view(models.NutanixCluster)
class NutanixClusterView(generic.ObjectView):
    queryset = models.NutanixCluster.objects.all()

    def get_extra_context(self, request, instance):
        return {
            'hosts_table': tables.NutanixHostTable(instance.hosts.all(), orderable=False),
            'vms_table': tables.NutanixVirtualMachineTable(
                instance.virtual_machines.all(), orderable=False
            ),
        }


class NutanixClusterListView(generic.ObjectListView):
    queryset = models.NutanixCluster.objects.all()
    table = tables.NutanixClusterTable
    filterset = filtersets.NutanixClusterFilterSet
    filterset_form = forms.NutanixClusterFilterForm
    actions = (AddObject, BulkImport, BulkExport, BulkEdit, BulkDelete)


@register_model_view(models.NutanixCluster, 'edit')
class NutanixClusterEditView(generic.ObjectEditView):
    queryset = models.NutanixCluster.objects.all()
    form = forms.NutanixClusterForm


@register_model_view(models.NutanixCluster, 'delete')
class NutanixClusterDeleteView(generic.ObjectDeleteView):
    queryset = models.NutanixCluster.objects.all()


class NutanixClusterBulkImportView(generic.BulkImportView):
    queryset = models.NutanixCluster.objects.all()
    model_form = forms.NutanixClusterImportForm


class NutanixClusterBulkEditView(generic.BulkEditView):
    queryset = models.NutanixCluster.objects.all()
    filterset = filtersets.NutanixClusterFilterSet
    table = tables.NutanixClusterTable
    form = forms.NutanixClusterBulkEditForm


class NutanixClusterBulkDeleteView(generic.BulkDeleteView):
    queryset = models.NutanixCluster.objects.all()
    filterset = filtersets.NutanixClusterFilterSet
    table = tables.NutanixClusterTable


class NutanixClusterSyncView(View):
    """
    Enqueue a background synchronization job for a single endpoint.
    """

    def post(self, request, pk):
        endpoint = get_object_or_404(
            models.NutanixCluster.objects.restrict(request.user, 'change'), pk=pk
        )

        sync_hosts = request.POST.get('sync_hosts', 'true') != 'false'
        sync_vms = request.POST.get('sync_vms', 'true') != 'false'

        NutanixSyncJob.enqueue(
            instance=endpoint,
            user=request.user,
            name=f"Nutanix sync: {endpoint}",
            cluster_pk=endpoint.pk,
            sync_hosts=sync_hosts,
            sync_vms=sync_vms,
        )

        messages.success(request, f"Synchronization job enqueued for '{endpoint}'.")
        return redirect(endpoint.get_absolute_url())


#
# Hosts
#

class NutanixHostListView(generic.ObjectListView):
    queryset = models.NutanixHost.objects.all()
    table = tables.NutanixHostTable
    filterset = filtersets.NutanixHostFilterSet
    filterset_form = forms.NutanixHostFilterForm
    actions = (BulkExport, BulkDelete)


@register_model_view(models.NutanixHost)
class NutanixHostView(generic.ObjectView):
    queryset = models.NutanixHost.objects.all()
    actions = (DeleteObject,)


@register_model_view(models.NutanixHost, 'delete')
class NutanixHostDeleteView(generic.ObjectDeleteView):
    queryset = models.NutanixHost.objects.all()


class NutanixHostBulkDeleteView(generic.BulkDeleteView):
    queryset = models.NutanixHost.objects.all()
    filterset = filtersets.NutanixHostFilterSet
    table = tables.NutanixHostTable


#
# Virtual machines
#

class NutanixVMListView(generic.ObjectListView):
    queryset = models.NutanixVirtualMachine.objects.all()
    table = tables.NutanixVirtualMachineTable
    filterset = filtersets.NutanixVirtualMachineFilterSet
    filterset_form = forms.NutanixVirtualMachineFilterForm
    actions = (BulkExport, BulkDelete)


@register_model_view(models.NutanixVirtualMachine)
class NutanixVMView(generic.ObjectView):
    queryset = models.NutanixVirtualMachine.objects.all()
    actions = (DeleteObject,)

    def get_extra_context(self, request, instance):
        return {
            'disks_table': tables.NutanixDiskTable(instance.disks.all(), orderable=False),
        }


@register_model_view(models.NutanixVirtualMachine, 'delete')
class NutanixVMDeleteView(generic.ObjectDeleteView):
    queryset = models.NutanixVirtualMachine.objects.all()


class NutanixVMBulkDeleteView(generic.BulkDeleteView):
    queryset = models.NutanixVirtualMachine.objects.all()
    filterset = filtersets.NutanixVirtualMachineFilterSet
    table = tables.NutanixVirtualMachineTable


#
# Disks
#

class NutanixDiskListView(generic.ObjectListView):
    queryset = models.NutanixDisk.objects.all()
    table = tables.NutanixDiskTable
    filterset = filtersets.NutanixDiskFilterSet
    filterset_form = forms.NutanixDiskFilterForm
    actions = (BulkExport, BulkDelete)


@register_model_view(models.NutanixDisk)
class NutanixDiskView(generic.ObjectView):
    queryset = models.NutanixDisk.objects.all()
    actions = (DeleteObject,)


@register_model_view(models.NutanixDisk, 'delete')
class NutanixDiskDeleteView(generic.ObjectDeleteView):
    queryset = models.NutanixDisk.objects.all()


class NutanixDiskBulkDeleteView(generic.BulkDeleteView):
    queryset = models.NutanixDisk.objects.all()
    filterset = filtersets.NutanixDiskFilterSet
    table = tables.NutanixDiskTable
