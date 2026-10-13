from netbox.plugins import PluginMenu, PluginMenuItem

menu = PluginMenu(
    label='SNMP',
    groups=(
        (
            'Discovery',
            (
                PluginMenuItem(
                    link='plugins:netbox_snmp:snmpendpoint_list',
                    link_text='Endpoints',
                    permissions=['netbox_snmp.view_snmpendpoint'],
                ),
                PluginMenuItem(
                    link='plugins:netbox_snmp:snmptarget_list',
                    link_text='Targets',
                    permissions=['netbox_snmp.view_snmptarget'],
                ),
                PluginMenuItem(
                    link='plugins:netbox_snmp:snmpdevice_list',
                    link_text='Devices',
                    permissions=['netbox_snmp.view_snmpdevice'],
                ),
            ),
        ),
    ),
    icon_class='mdi mdi-lan-connect',
)
