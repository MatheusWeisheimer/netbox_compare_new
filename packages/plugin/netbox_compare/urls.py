from django.urls import include, path
from utilities.urls import get_model_urls

from . import views

urlpatterns = [
    path("runs/", include(get_model_urls("netbox_compare", "comparisonrun", detail=False))),
    path("runs/<int:pk>/", include(get_model_urls("netbox_compare", "comparisonrun"))),
    path("commands/", include(get_model_urls("netbox_compare", "commandlog", detail=False))),
    path("commands/<int:pk>/", include(get_model_urls("netbox_compare", "commandlog"))),
    path(
        "schedules/", include(get_model_urls("netbox_compare", "comparisonschedule", detail=False))
    ),
    path("schedules/<int:pk>/", include(get_model_urls("netbox_compare", "comparisonschedule"))),
    path("policy/", views.global_policy_view, name="comparisonpolicy_list"),
    path("policy/<int:pk>/", include(get_model_urls("netbox_compare", "comparisonpolicy"))),
    path("devices/<int:pk>/compare/", views.CompareDeviceView.as_view(), name="device_compare"),
]
