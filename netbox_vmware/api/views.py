from rest_framework.decorators import action
from rest_framework.response import Response

from netbox.api.viewsets import NetBoxModelViewSet

from .. import filtersets, models
from ..jobs import VMwareSyncJob
from . import serializers


class VMwareEndpointViewSet(NetBoxModelViewSet):
    queryset = models.VMwareEndpoint.objects.all()
    serializer_class = serializers.VMwareEndpointSerializer
    filterset_class = filtersets.VMwareEndpointFilterSet

    @action(detail=True, methods=['post'])
    def sync(self, request, pk=None):
        endpoint = self.get_object()
        VMwareSyncJob.enqueue(
            instance=endpoint,
            user=request.user,
            name=f"VMware sync: {endpoint}",
            cluster_pk=endpoint.pk,
            sync_hosts=request.data.get('sync_hosts', True),
            sync_vms=request.data.get('sync_vms', True),
        )
        return Response({'detail': 'Synchronization job enqueued.'}, status=202)


class VMwareHostViewSet(NetBoxModelViewSet):
    queryset = models.VMwareHost.objects.all()
    serializer_class = serializers.VMwareHostSerializer
    filterset_class = filtersets.VMwareHostFilterSet


class VMwareVirtualMachineViewSet(NetBoxModelViewSet):
    queryset = models.VMwareVirtualMachine.objects.all()
    serializer_class = serializers.VMwareVirtualMachineSerializer
    filterset_class = filtersets.VMwareVirtualMachineFilterSet


class VMwareDiskViewSet(NetBoxModelViewSet):
    queryset = models.VMwareDisk.objects.all()
    serializer_class = serializers.VMwareDiskSerializer
    filterset_class = filtersets.VMwareDiskFilterSet
