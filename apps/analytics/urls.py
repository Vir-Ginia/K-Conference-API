"""URL routing for the Analytics app."""
from rest_framework.routers import DefaultRouter
from apps.analytics.views import AnalyticsViewSet

router = DefaultRouter()
router.register(r'analytics', AnalyticsViewSet, basename='analytics')

urlpatterns = router.urls
