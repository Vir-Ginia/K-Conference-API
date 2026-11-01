"""
URL routing for user profile and management endpoints
"""

from django.urls import path, include
from rest_framework.routers import SimpleRouter
from apps.accounts.views import UserProfileViewSet, UserManagementViewSet, ProfilePictureUploadView

router = SimpleRouter()

# Register admin user management ViewSet
router.register(r'admin/users', UserManagementViewSet, basename='user-management')

# Custom URL patterns for user profile
urlpatterns = [
    path('me/', UserProfileViewSet.as_view({'get': 'get_current_user', 'patch': 'update_current_user'}), name='current-user'),
    path('me/picture/', ProfilePictureUploadView.as_view(), name='profile-picture'),
    path('<uuid:pk>/', UserProfileViewSet.as_view({'get': 'retrieve_user'}), name='user-detail'),
] + router.urls
