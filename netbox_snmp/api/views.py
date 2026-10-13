from rest_framework.decorators import action
from rest_framework.response import Response

from netbox.api.viewsets import NetBoxModelViewSet

from .. import filtersets, models
from ..jobs import SnmpSyncJob
from . import serializers


class SnmpEndpointViewSet(NetBoxModelViewSet):
    queryset = models.SnmpEndpoint.objects.all()
    serializer_class = serializers.SnmpEndpointSerializer
    filterset_class = filtersets.SnmpEndpointFilterSet

    @action(detail=True, methods=['post'])
    def sync(self, request, pk=None):
        endpoint = self.get_object()
        SnmpSyncJob.enqueue(
            instance=endpoint,
            user=request.user,
            name=f"SNMP sync: {endpoint}",
            endpoint_pk=endpoint.pk,
        )
        return Response({'detail': 'Discovery job enqueued.'}, status=202)


class SnmpTargetViewSet(NetBoxModelViewSet):
    queryset = models.SnmpTarget.objects.all()
    serializer_class = serializers.SnmpTargetSerializer
    filterset_class = filtersets.SnmpTargetFilterSet


class SnmpDeviceViewSet(NetBoxModelViewSet):
    queryset = models.SnmpDevice.objects.all()
    serializer_class = serializers.SnmpDeviceSerializer
    filterset_class = filtersets.SnmpDeviceFilterSet
