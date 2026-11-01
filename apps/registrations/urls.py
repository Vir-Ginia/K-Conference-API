"""URL routing for the Registrations app."""
from rest_framework.routers import DefaultRouter
from apps.registrations.views import RegistrationViewSet

router = DefaultRouter()
router.register(r'registrations', RegistrationViewSet, basename='registration')

urlpatterns = router.urls
