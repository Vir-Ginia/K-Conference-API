"""
URL routing for Conferences App
API endpoints for conference management.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.conferences.views import (
    ConferenceViewSet, ConferenceTrackViewSet,
    ConferenceDeadlineViewSet, ConferenceRoleViewSet,
    ReviewRubricViewSet, ConferenceMediaViewSet
)

# Main router for conferences
router = DefaultRouter()
router.register(r'conferences', ConferenceViewSet, basename='conference')
router.register(r'tracks', ConferenceTrackViewSet, basename='tracks')
router.register(r'deadlines', ConferenceDeadlineViewSet, basename='deadlines')
router.register(r'roles', ConferenceRoleViewSet, basename='roles')
router.register(r'rubrics', ReviewRubricViewSet, basename='rubrics')
router.register(r'media', ConferenceMediaViewSet, basename='media')

urlpatterns = router.urls
