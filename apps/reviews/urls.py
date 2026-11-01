"""URL routing for the Reviews app."""
from rest_framework.routers import DefaultRouter
from apps.reviews.views import (
    ReviewAssignmentViewSet, ConflictOfInterestViewSet,
    ReviewViewSet, ReviewDecisionViewSet,
)

router = DefaultRouter()
router.register(r'assignments', ReviewAssignmentViewSet, basename='review-assignment')
router.register(r'conflicts', ConflictOfInterestViewSet, basename='conflict-of-interest')
router.register(r'reviews', ReviewViewSet, basename='review')
router.register(r'decisions', ReviewDecisionViewSet, basename='review-decision')

urlpatterns = router.urls
