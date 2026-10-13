from django.urls import path

from netbox.views.generic import ObjectChangeLogView, ObjectJobsView

from . import models, views

urlpatterns = (
    # Endpoints
    path('clusters/', views.VMwareEndpointListView.as_view(), name='vmwareendpoint_list'),
    path('clusters/add/', views.VMwareEndpointEditView.as_view(), name='vmwareendpoint_add'),
    path('clusters/import/', views.VMwareEndpointBulkImportView.as_view(), name='vmwareendpoint_bulk_import'),
    path('clusters/edit/', views.VMwareEndpointBulkEditView.as_view(), name='vmwareendpoint_bulk_edit'),
    path('clusters/delete/', views.VMwareEndpointBulkDeleteView.as_view(), name='vmwareendpoint_bulk_delete'),
    path('clusters/<int:pk>/', views.VMwareEndpointView.as_view(), name='vmwareendpoint'),
    path('clusters/<int:pk>/edit/', views.VMwareEndpointEditView.as_view(), name='vmwareendpoint_edit'),
    path('clusters/<int:pk>/delete/', views.VMwareEndpointDeleteView.as_view(), name='vmwareendpoint_delete'),
    path('clusters/<int:pk>/sync/', views.VMwareEndpointSyncView.as_view(), name='vmwareendpoint_sync'),
    path(
        'clusters/<int:pk>/changelog/', ObjectChangeLogView.as_view(),
        name='vmwareendpoint_changelog', kwargs={'model': models.VMwareEndpoint},
    ),
    path(
        'clusters/<int:pk>/jobs/', ObjectJobsView.as_view(),
        name='vmwareendpoint_jobs', kwargs={'model': models.VMwareEndpoint},
    ),

    # Hosts
    path('hosts/', views.VMwareHostListView.as_view(), name='vmwarehost_list'),
    path('hosts/delete/', views.VMwareHostBulkDeleteView.as_view(), name='vmwarehost_bulk_delete'),
    path('hosts/<int:pk>/', views.VMwareHostView.as_view(), name='vmwarehost'),
    path('hosts/<int:pk>/delete/', views.VMwareHostDeleteView.as_view(), name='vmwarehost_delete'),
    path(
        'hosts/<int:pk>/changelog/', ObjectChangeLogView.as_view(),
        name='vmwarehost_changelog', kwargs={'model': models.VMwareHost},
    ),

    # Virtual machines
    path('vms/', views.VMwareVMListView.as_view(), name='vmwarevirtualmachine_list'),
    path('vms/delete/', views.VMwareVMBulkDeleteView.as_view(), name='vmwarevirtualmachine_bulk_delete'),
    path('vms/<int:pk>/', views.VMwareVMView.as_view(), name='vmwarevirtualmachine'),
    path('vms/<int:pk>/delete/', views.VMwareVMDeleteView.as_view(), name='vmwarevirtualmachine_delete'),
    path(
        'vms/<int:pk>/changelog/', ObjectChangeLogView.as_view(),
        name='vmwarevirtualmachine_changelog', kwargs={'model': models.VMwareVirtualMachine},
    ),

    # Disks
    path('disks/', views.VMwareDiskListView.as_view(), name='vmwaredisk_list'),
    path('disks/delete/', views.VMwareDiskBulkDeleteView.as_view(), name='vmwaredisk_bulk_delete'),
    path('disks/<int:pk>/', views.VMwareDiskView.as_view(), name='vmwaredisk'),
    path('disks/<int:pk>/delete/', views.VMwareDiskDeleteView.as_view(), name='vmwaredisk_delete'),
    path(
        'disks/<int:pk>/changelog/', ObjectChangeLogView.as_view(),
        name='vmwaredisk_changelog', kwargs={'model': models.VMwareDisk},
    ),
)
