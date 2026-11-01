"""Submission-specific permissions."""
from rest_framework import permissions


class IsSubmissionOwner(permissions.BasePermission):
    """Only the user who submitted the paper can edit/delete it."""

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.submitted_by == request.user


class CanViewSubmission(permissions.BasePermission):
    """
    Defines who can view a submission:
    - The submitting author
    - The conference organiser
    - An assigned reviewer (checked via ReviewAssignment)
    - Admin
    """

    def has_object_permission(self, request, view, obj):
        user = request.user

        if user.is_admin or user.is_superuser:
            return True

        if obj.submitted_by == user:
            return True

        if obj.conference.organiser == user:
            return True

        # Assigned reviewer
        try:
            from apps.reviews.models import ReviewAssignment
            return ReviewAssignment.objects.filter(
                submission=obj,
                reviewer=user,
                is_active=True
            ).exists()
        except Exception:
            return False


class IsConferenceOrganiserForSubmission(permissions.BasePermission):
    """Only the organiser of the submission's conference can perform this action."""

    def has_object_permission(self, request, view, obj):
        user = request.user
        return user.is_admin or obj.conference.organiser == user
