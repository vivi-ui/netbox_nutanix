from django.urls import path

from netbox.views.generic import ObjectChangeLogView, ObjectJobsView

from . import models, views

urlpatterns = (
    # Endpoints
    path('endpoints/', views.SnmpEndpointListView.as_view(), name='snmpendpoint_list'),
    path('endpoints/add/', views.SnmpEndpointEditView.as_view(), name='snmpendpoint_add'),
    path('endpoints/import/', views.SnmpEndpointBulkImportView.as_view(), name='snmpendpoint_bulk_import'),
    path('endpoints/edit/', views.SnmpEndpointBulkEditView.as_view(), name='snmpendpoint_bulk_edit'),
    path('endpoints/delete/', views.SnmpEndpointBulkDeleteView.as_view(), name='snmpendpoint_bulk_delete'),
    path('endpoints/<int:pk>/', views.SnmpEndpointView.as_view(), name='snmpendpoint'),
    path('endpoints/<int:pk>/edit/', views.SnmpEndpointEditView.as_view(), name='snmpendpoint_edit'),
    path('endpoints/<int:pk>/delete/', views.SnmpEndpointDeleteView.as_view(), name='snmpendpoint_delete'),
    path('endpoints/<int:pk>/sync/', views.SnmpEndpointSyncView.as_view(), name='snmpendpoint_sync'),
    path('endpoints/<int:pk>/cancel/', views.SnmpEndpointCancelView.as_view(), name='snmpendpoint_cancel'),
    path(
        'endpoints/<int:pk>/changelog/', ObjectChangeLogView.as_view(),
        name='snmpendpoint_changelog', kwargs={'model': models.SnmpEndpoint},
    ),
    path(
        'endpoints/<int:pk>/jobs/', ObjectJobsView.as_view(),
        name='snmpendpoint_jobs', kwargs={'model': models.SnmpEndpoint},
    ),

    # Targets
    path('targets/', views.SnmpTargetListView.as_view(), name='snmptarget_list'),
    path('targets/add/', views.SnmpTargetMultiAddView.as_view(), name='snmptarget_add'),
    path('targets/import/', views.SnmpTargetBulkImportView.as_view(), name='snmptarget_bulk_import'),
    path('targets/edit/', views.SnmpTargetBulkEditView.as_view(), name='snmptarget_bulk_edit'),
    path('targets/delete/', views.SnmpTargetBulkDeleteView.as_view(), name='snmptarget_bulk_delete'),
    path('targets/<int:pk>/', views.SnmpTargetView.as_view(), name='snmptarget'),
    path('targets/<int:pk>/edit/', views.SnmpTargetEditView.as_view(), name='snmptarget_edit'),
    path('targets/<int:pk>/delete/', views.SnmpTargetDeleteView.as_view(), name='snmptarget_delete'),
    path(
        'targets/<int:pk>/changelog/', ObjectChangeLogView.as_view(),
        name='snmptarget_changelog', kwargs={'model': models.SnmpTarget},
    ),

    # Devices
    path('devices/', views.SnmpDeviceListView.as_view(), name='snmpdevice_list'),
    path('devices/delete/', views.SnmpDeviceBulkDeleteView.as_view(), name='snmpdevice_bulk_delete'),
    path('devices/<int:pk>/', views.SnmpDeviceView.as_view(), name='snmpdevice'),
    path('devices/<int:pk>/delete/', views.SnmpDeviceDeleteView.as_view(), name='snmpdevice_delete'),
    path(
        'devices/<int:pk>/changelog/', ObjectChangeLogView.as_view(),
        name='snmpdevice_changelog', kwargs={'model': models.SnmpDevice},
    ),
)
