from netbox.api.routers import NetBoxRouter

from . import views

router = NetBoxRouter()
router.register('endpoints', views.SnmpEndpointViewSet)
router.register('targets', views.SnmpTargetViewSet)
router.register('devices', views.SnmpDeviceViewSet)

urlpatterns = router.urls
