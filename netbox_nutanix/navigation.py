from netbox.plugins import PluginMenu, PluginMenuItem

menu = PluginMenu(
    label='Nutanix',
    groups=(
        (
            'Synchronization',
            (
                PluginMenuItem(
                    link='plugins:netbox_nutanix:nutanixcluster_list',
                    link_text='Endpoints',
                    permissions=['netbox_nutanix.view_nutanixcluster'],
                ),
                PluginMenuItem(
                    link='plugins:netbox_nutanix:nutanixhost_list',
                    link_text='Hosts',
                    permissions=['netbox_nutanix.view_nutanixhost'],
                ),
                PluginMenuItem(
                    link='plugins:netbox_nutanix:nutanixvirtualmachine_list',
                    link_text='Virtual Machines',
                    permissions=['netbox_nutanix.view_nutanixvirtualmachine'],
                ),
                PluginMenuItem(
                    link='plugins:netbox_nutanix:nutanixdisk_list',
                    link_text='Disks',
                    permissions=['netbox_nutanix.view_nutanixdisk'],
                ),
            ),
        ),
    ),
    icon_class='mdi mdi-cloud-sync',
)
