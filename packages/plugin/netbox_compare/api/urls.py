from netbox.api.routers import NetBoxRouter

from . import views

router = NetBoxRouter()
router.APIRootView = views.NetBoxCompareRootView
router.register("runs", views.ComparisonRunViewSet)
router.register("divergences", views.DivergenceViewSet)
router.register("commands", views.CommandLogViewSet)
router.register("policy", views.ComparisonPolicyViewSet)

urlpatterns = router.urls
