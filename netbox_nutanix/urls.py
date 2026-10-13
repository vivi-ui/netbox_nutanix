from django.urls import path

from netbox.views.generic import ObjectChangeLogView, ObjectJobsView

from . import models, views

urlpatterns = (
    # Endpoints
    path('clusters/', views.NutanixClusterListView.as_view(), name='nutanixcluster_list'),
    path('clusters/add/', views.NutanixClusterEditView.as_view(), name='nutanixcluster_add'),
    path('clusters/import/', views.NutanixClusterBulkImportView.as_view(), name='nutanixcluster_bulk_import'),
    path('clusters/edit/', views.NutanixClusterBulkEditView.as_view(), name='nutanixcluster_bulk_edit'),
    path('clusters/delete/', views.NutanixClusterBulkDeleteView.as_view(), name='nutanixcluster_bulk_delete'),
    path('clusters/<int:pk>/', views.NutanixClusterView.as_view(), name='nutanixcluster'),
    path('clusters/<int:pk>/edit/', views.NutanixClusterEditView.as_view(), name='nutanixcluster_edit'),
    path('clusters/<int:pk>/delete/', views.NutanixClusterDeleteView.as_view(), name='nutanixcluster_delete'),
    path('clusters/<int:pk>/sync/', views.NutanixClusterSyncView.as_view(), name='nutanixcluster_sync'),
    path(
        'clusters/<int:pk>/changelog/', ObjectChangeLogView.as_view(),
        name='nutanixcluster_changelog', kwargs={'model': models.NutanixCluster},
    ),
    path(
        'clusters/<int:pk>/jobs/', ObjectJobsView.as_view(),
        name='nutanixcluster_jobs', kwargs={'model': models.NutanixCluster},
    ),

    # Hosts
    path('hosts/', views.NutanixHostListView.as_view(), name='nutanixhost_list'),
    path('hosts/delete/', views.NutanixHostBulkDeleteView.as_view(), name='nutanixhost_bulk_delete'),
    path('hosts/<int:pk>/', views.NutanixHostView.as_view(), name='nutanixhost'),
    path('hosts/<int:pk>/delete/', views.NutanixHostDeleteView.as_view(), name='nutanixhost_delete'),
    path(
        'hosts/<int:pk>/changelog/', ObjectChangeLogView.as_view(),
        name='nutanixhost_changelog', kwargs={'model': models.NutanixHost},
    ),

    # Virtual machines
    path('vms/', views.NutanixVMListView.as_view(), name='nutanixvirtualmachine_list'),
    path('vms/delete/', views.NutanixVMBulkDeleteView.as_view(), name='nutanixvirtualmachine_bulk_delete'),
    path('vms/<int:pk>/', views.NutanixVMView.as_view(), name='nutanixvirtualmachine'),
    path('vms/<int:pk>/delete/', views.NutanixVMDeleteView.as_view(), name='nutanixvirtualmachine_delete'),
    path(
        'vms/<int:pk>/changelog/', ObjectChangeLogView.as_view(),
        name='nutanixvirtualmachine_changelog', kwargs={'model': models.NutanixVirtualMachine},
    ),

    # Disks
    path('disks/', views.NutanixDiskListView.as_view(), name='nutanixdisk_list'),
    path('disks/delete/', views.NutanixDiskBulkDeleteView.as_view(), name='nutanixdisk_bulk_delete'),
    path('disks/<int:pk>/', views.NutanixDiskView.as_view(), name='nutanixdisk'),
    path('disks/<int:pk>/delete/', views.NutanixDiskDeleteView.as_view(), name='nutanixdisk_delete'),
    path(
        'disks/<int:pk>/changelog/', ObjectChangeLogView.as_view(),
        name='nutanixdisk_changelog', kwargs={'model': models.NutanixDisk},
    ),
)
