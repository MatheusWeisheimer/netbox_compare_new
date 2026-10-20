from django.utils.translation import gettext_lazy as _
from netbox.plugins import PluginMenu, PluginMenuButton, PluginMenuItem

menu = PluginMenu(
    label=_("Compare"),
    icon_class="mdi mdi-compare-horizontal",
    groups=(
        (
            _("Comparisons"),
            (
                PluginMenuItem(
                    link="plugins:netbox_compare:comparisonrun_list",
                    link_text=_("Runs"),
                    permissions=["netbox_compare.view_comparisonrun"],
                ),
                PluginMenuItem(
                    link="plugins:netbox_compare:comparisonschedule_list",
                    link_text=_("Schedules"),
                    permissions=["netbox_compare.view_comparisonschedule"],
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_compare:comparisonschedule_add",
                            title=_("Add"),
                            icon_class="mdi mdi-plus-thick",
                            permissions=["netbox_compare.add_comparisonschedule"],
                        ),
                    ),
                ),
                PluginMenuItem(
                    link="plugins:netbox_compare:comparisonpolicy_list",
                    link_text=_("Policy"),
                    permissions=["netbox_compare.view_comparisonpolicy"],
                ),
            ),
        ),
    ),
)
