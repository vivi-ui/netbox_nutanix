from netbox.api.routers import NetBoxRouter

from . import views

router = NetBoxRouter()
router.register('clusters', views.VMwareEndpointViewSet)
router.register('hosts', views.VMwareHostViewSet)
router.register('vms', views.VMwareVirtualMachineViewSet)
router.register('disks', views.VMwareDiskViewSet)

urlpatterns = router.urls
