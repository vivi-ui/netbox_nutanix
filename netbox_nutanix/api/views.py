from rest_framework.decorators import action
from rest_framework.response import Response

from netbox.api.viewsets import NetBoxModelViewSet

from .. import filtersets, models
from ..jobs import NutanixSyncJob
from . import serializers


class NutanixClusterViewSet(NetBoxModelViewSet):
    queryset = models.NutanixCluster.objects.all()
    serializer_class = serializers.NutanixClusterSerializer
    filterset_class = filtersets.NutanixClusterFilterSet

    @action(detail=True, methods=['post'])
    def sync(self, request, pk=None):
        endpoint = self.get_object()
        NutanixSyncJob.enqueue(
            instance=endpoint,
            user=request.user,
            name=f"Nutanix sync: {endpoint}",
            cluster_pk=endpoint.pk,
            sync_hosts=request.data.get('sync_hosts', True),
            sync_vms=request.data.get('sync_vms', True),
        )
        return Response({'detail': 'Synchronization job enqueued.'}, status=202)


class NutanixHostViewSet(NetBoxModelViewSet):
    queryset = models.NutanixHost.objects.all()
    serializer_class = serializers.NutanixHostSerializer
    filterset_class = filtersets.NutanixHostFilterSet


class NutanixVirtualMachineViewSet(NetBoxModelViewSet):
    queryset = models.NutanixVirtualMachine.objects.all()
    serializer_class = serializers.NutanixVirtualMachineSerializer
    filterset_class = filtersets.NutanixVirtualMachineFilterSet


class NutanixDiskViewSet(NetBoxModelViewSet):
    queryset = models.NutanixDisk.objects.all()
    serializer_class = serializers.NutanixDiskSerializer
    filterset_class = filtersets.NutanixDiskFilterSet
