from netbox.plugins import PluginMenu, PluginMenuItem

menu = PluginMenu(
    label='VMware',
    groups=(
        (
            'Synchronization',
            (
                PluginMenuItem(
                    link='plugins:netbox_vmware:vmwareendpoint_list',
                    link_text='Endpoints',
                    permissions=['netbox_vmware.view_vmwareendpoint'],
                ),
                PluginMenuItem(
                    link='plugins:netbox_vmware:vmwarehost_list',
                    link_text='Hosts',
                    permissions=['netbox_vmware.view_vmwarehost'],
                ),
                PluginMenuItem(
                    link='plugins:netbox_vmware:vmwarevirtualmachine_list',
                    link_text='Virtual Machines',
                    permissions=['netbox_vmware.view_vmwarevirtualmachine'],
                ),
                PluginMenuItem(
                    link='plugins:netbox_vmware:vmwaredisk_list',
                    link_text='Disks',
                    permissions=['netbox_vmware.view_vmwaredisk'],
                ),
            ),
        ),
    ),
    icon_class='mdi mdi-cloud-sync',
)
