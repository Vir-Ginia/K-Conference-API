"""
Conference-Specific Permissions
Role-based access control for conference management operations.
"""

from rest_framework import permissions
from apps.conferences.models import ConferenceRole


class IsConferenceOrganiser(permissions.BasePermission):
    """
    Allow only the organiser of a conference to manage it.
    """

    def has_object_permission(self, request, view, obj):
        if hasattr(obj, 'organiser'):
            return obj.organiser == request.user
        return False


class IsConferenceOrganiserOrAdmin(permissions.BasePermission):
    """
    Allow conference organiser or admin/superuser to manage conference.
    """

    def has_permission(self, request, view):
        """Check general permission - user must be authenticated."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser or request.user.is_admin:
            return True
        # Navigate to the conference for related objects (tracks, roles, media, rubrics, etc.)
        conference = obj
        if hasattr(obj, 'conference'):
            conference = obj.conference
        if hasattr(conference, 'organiser'):
            return conference.organiser == request.user
        return False


class IsTrackChair(permissions.BasePermission):
    """
    Allow only track chairs to manage their tracks.
    """

    def has_permission(self, request, view):
        """Check general permission - user must be authenticated."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if hasattr(obj, 'chair'):
            return obj.chair == request.user
        return False


class CanManageConference(permissions.BasePermission):
    """
    Allow users with conference management roles to access conference data.
    """

    def has_permission(self, request, view):
        """Check general permission - user must be authenticated."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser or request.user.is_admin:
            return True

        conference = obj
        if hasattr(obj, 'conference'):
            conference = obj.conference

        # The conference organiser always has full management access
        if hasattr(conference, 'organiser') and conference.organiser == request.user:
            return True

        # Users with any active role in this conference (chair, reviewer, etc.)
        return ConferenceRole.objects.filter(
            conference=conference,
            user=request.user,
            is_active=True
        ).exists()


class CanViewConference(permissions.BasePermission):
    """
    Allow viewing conference details.
    Public conferences can be viewed by anyone.
    Private conferences require participation or management role.
    """

    def has_permission(self, request, view):
        """Check permission for list actions - allow all users for schema introspection."""
        # Allow for schema generation and unauthenticated access
        return True

    def has_object_permission(self, request, view, obj):
        # obj is always a Conference here
        conference = obj

        # Public conferences are visible to everyone
        if conference.status in ['open', 'review', 'closed']:
            return True

        # Past this point the conference is draft/archived — requires authentication
        if not request.user or not request.user.is_authenticated:
            return False

        # Admins and the owning organiser always have access
        if request.user.is_superuser or request.user.is_admin:
            return True

        if conference.organiser == request.user:
            return True

        # Users with any active conference role also have access
        return ConferenceRole.objects.filter(
            conference=conference,
            user=request.user,
            is_active=True
        ).exists()


class CanCreateConference(permissions.BasePermission):
    """
    Allow only users with organiser role to create conferences.
    """

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_organiser


class IsConferenceParticipant(permissions.BasePermission):
    """
    Allow only registered participants to access participant-only features.
    """

    def has_object_permission(self, request, view, obj):
        conference = obj
        if hasattr(obj, 'conference'):
            conference = obj.conference

        return ConferenceRole.objects.filter(
            conference=conference,
            user=request.user,
            role='participant',
            is_active=True
        ).exists()


class CanOverrideDeadlines(permissions.BasePermission):
    """
    Only organisers can override deadlines.
    """

    def has_object_permission(self, request, view, obj):
        conference = obj
        if hasattr(obj, 'conference'):
            conference = obj.conference

        return conference.organiser == request.user or request.user.is_superuser or request.user.is_admin