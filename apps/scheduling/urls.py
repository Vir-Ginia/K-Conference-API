"""URL routing for the Scheduling app."""
from rest_framework.routers import DefaultRouter
from apps.scheduling.views import SessionViewSet

router = DefaultRouter()
router.register(r'sessions', SessionViewSet, basename='session')

urlpatterns = router.urls
