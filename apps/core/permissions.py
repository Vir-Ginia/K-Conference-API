"""
Role-Based Access Control (RBAC) Permissions
Implements fine-grained permission checking at endpoint and object levels.
"""

from rest_framework import permissions
from apps.accounts.models import User


class IsAuthor(permissions.BasePermission):
    """User is an author."""
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_author


class IsReviewer(permissions.BasePermission):
    """User is a reviewer."""
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_reviewer


class IsOrganiser(permissions.BasePermission):
    """User is an organiser."""
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_organiser


class IsParticipant(permissions.BasePermission):
    """User is a participant."""
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_participant


class IsAdminUser(permissions.BasePermission):
    """User is an admin."""
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_admin


class IsAdminOrSuperUser(permissions.BasePermission):
    """User is an admin or superuser."""
    
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            (request.user.is_admin or request.user.is_superuser)
        )


class IsAuthorOrReadOnly(permissions.BasePermission):
    """
    Allow authors to create/edit submissions.
    Non-authors can only read.
    """
    
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user and request.user.is_authenticated and request.user.is_author


class IsAuthorOfSubmission(permissions.BasePermission):
    """
    Allow only the author of a submission to edit it.
    """
    
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.author == request.user


class IsAssignedReviewer(permissions.BasePermission):
    """
    Allow only assigned reviewers to review a submission.
    """
    
    def has_object_permission(self, request, view, obj):
        # This is checked against a Review object
        return obj.reviewer == request.user


class IsReviewerOfSubmission(permissions.BasePermission):
    """
    Allow only reviewers assigned to this submission to view and review it.
    """
    
    def has_object_permission(self, request, view, obj):
        # obj is a Submission
        if request.user.is_organiser:
            return True
        
        # Check if user is assigned as a reviewer
        from apps.reviews.models import ReviewAssignment
        return ReviewAssignment.objects.filter(
            submission=obj,
            reviewer=request.user,
            is_active=True
        ).exists()


class IsConferenceOrganiser(permissions.BasePermission):
    """
    Allow only the organiser of a conference to manage it.
    """
    
    def has_object_permission(self, request, view, obj):
        return obj.organiser == request.user


class CanAccessConference(permissions.BasePermission):
    """
    Allow access to conference data based on user role and conference relationship.
    """
    
    def has_object_permission(self, request, view, obj):
        from apps.conferences.models import ConferenceRole
        
        if request.user.is_organiser:
            return True
        
        # Check if user has a role in this conference
        return ConferenceRole.objects.filter(
            conference=obj,
            user=request.user,
            is_active=True
        ).exists()


class IsDeadlineNotPassed(permissions.BasePermission):
    """
    Check if submission deadline has not passed.
    Used for preventing late submissions.
    """
    
    def has_object_permission(self, request, view, obj):
        from django.utils import timezone
        return obj.submission_deadline > timezone.now()


class CanOverrideDeadline(permissions.BasePermission):
    """
    Only organisers can override deadlines.
    """
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_organiser
