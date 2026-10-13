from netbox.api.routers import NetBoxRouter

from . import views

router = NetBoxRouter()
router.register('clusters', views.NutanixClusterViewSet)
router.register('hosts', views.NutanixHostViewSet)
router.register('vms', views.NutanixVirtualMachineViewSet)
router.register('disks', views.NutanixDiskViewSet)

urlpatterns = router.urls
