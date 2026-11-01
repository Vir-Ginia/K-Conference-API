"""URL routing for communications."""
from rest_framework.routers import DefaultRouter
from apps.communications.views import NotificationViewSet, AnnouncementViewSet, FAQItemViewSet

router = DefaultRouter()
router.register(r'notifications', NotificationViewSet, basename='notification')
router.register(r'announcements', AnnouncementViewSet, basename='announcement')
router.register(r'faq', FAQItemViewSet, basename='faq')

urlpatterns = router.urls
