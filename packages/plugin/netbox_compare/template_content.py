from netbox.plugins import PluginTemplateExtension

from .credentials import has_credentials
from .models import ComparisonRun


class DeviceComparison(PluginTemplateExtension):
    models = ["dcim.device"]

    def buttons(self):
        user = self.context["request"].user
        if not user.has_perm("netbox_compare.add_comparisonrun"):
            return ""
        if not has_credentials(self.context["object"]):
            return ""
        return self.render("netbox_compare/inc/device_compare_button.html")

    def right_page(self):
        user = self.context["request"].user
        if not user.has_perm("netbox_compare.view_comparisonrun"):
            return ""
        latest = (
            ComparisonRun.objects.restrict(user, "view")
            .filter(device=self.context["object"])
            .first()
        )
        return self.render(
            "netbox_compare/inc/device_comparison_panel.html",
            extra_context={
                "run": latest,
                "has_credentials": has_credentials(self.context["object"]),
            },
        )


template_extensions = [DeviceComparison]
