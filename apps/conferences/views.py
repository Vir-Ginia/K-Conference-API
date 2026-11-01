"""
Views for Conference Management
API endpoints for conference lifecycle management.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db import models
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes

from apps.conferences.models import (
    Conference, ConferenceTrack, ConferenceDeadline,
    ConferenceRole, ReviewRubric, ConferenceMedia
)
from apps.conferences.serializers import (
    ConferenceListSerializer, ConferenceDetailSerializer,
    ConferenceCreateSerializer, ConferenceUpdateSerializer,
    ConferenceTrackSerializer, ConferenceDeadlineSerializer,
    ConferenceRoleSerializer, ReviewRubricSerializer,
    ConferenceMediaSerializer, ConferenceMediaUploadSerializer
)
from apps.conferences.permissions import (
    CanCreateConference, IsConferenceOrganiserOrAdmin,
    CanViewConference, CanManageConference
)


class ConferenceViewSet(viewsets.ModelViewSet):
    """
    ViewSet for conference management.
    Supports full CRUD operations with role-based permissions.
    """

    queryset = Conference.objects.all()
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'conference_type', 'organiser', 'is_active']
    search_fields = ['title', 'short_name', 'description', 'city', 'country']
    ordering_fields = ['start_date', 'end_date', 'created_at', 'title']
    ordering = ['-start_date']

    def get_queryset(self):
        """Filter conferences based on user permissions."""
        user = self.request.user

        # For retrieve action, allow access to public conferences even for unauthenticated users
        if self.action == 'retrieve':
            if user.is_authenticated:
                # If user is admin/superuser, show all conferences
                if user.is_superuser or user.is_admin:
                    return Conference.objects.all()

                # If user is organiser, show their conferences and public conferences and conferences they participate in
                if user.is_organiser:
                    return Conference.objects.filter(
                        models.Q(organiser=user) |
                        models.Q(status__in=['open', 'review', 'closed']) |
                        (models.Q(user_roles__user=user) & models.Q(user_roles__is_active=True))
                    ).distinct()

                # For regular authenticated users, show public conferences and conferences they participate in
                public_conferences = Conference.objects.filter(
                    status__in=['open', 'review', 'closed']
                )
                user_conferences = Conference.objects.filter(
                    user_roles__user=user,
                    user_roles__is_active=True
                )
                return (public_conferences | user_conferences).distinct()
            else:
                # For unauthenticated users, only show public conferences
                return Conference.objects.filter(status__in=['open', 'review', 'closed'])

        # For other actions, require authentication
        # If user is admin/superuser, show all conferences
        if user.is_superuser or user.is_admin:
            return Conference.objects.all()

        # If user is organiser, show their conferences and public conferences and conferences they participate in
        if user.is_organiser:
            return Conference.objects.filter(
                models.Q(organiser=user) |
                models.Q(status__in=['open', 'review', 'closed']) |
                (models.Q(user_roles__user=user) & models.Q(user_roles__is_active=True))
            ).distinct()

        # For regular users, show public conferences and conferences they participate in
        public_conferences = Conference.objects.filter(
            status__in=['open', 'review', 'closed']
        )

        # Conferences where user has a role
        user_conferences = Conference.objects.filter(
            user_roles__user=user,
            user_roles__is_active=True
        )

        return (public_conferences | user_conferences).distinct()

    def get_serializer_class(self):
        if self.action == 'create':
            return ConferenceCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return ConferenceUpdateSerializer
        elif self.action == 'list':
            return ConferenceListSerializer
        return ConferenceDetailSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [IsAuthenticated(), CanCreateConference()]
        elif self.action in ['update', 'partial_update', 'destroy', 'change_status']:
            return [IsAuthenticated(), IsConferenceOrganiserOrAdmin()]
        elif self.action == 'retrieve':
            return [AllowAny()]
        elif self.action in ['list', 'statistics']:
            return [CanViewConference()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        """Set the organiser when creating a conference and auto-create their ConferenceRole."""
        conference = serializer.save(organiser=self.request.user)
        ConferenceRole.objects.get_or_create(
            conference=conference,
            user=self.request.user,
            defaults={
                'role': 'organiser',
                'assigned_by': self.request.user,
                'is_active': True,
            },
        )

    @extend_schema(
        request={'application/json': {'type': 'object', 'properties': {'status': {'type': 'string'}}, 'required': ['status']}},
        responses=ConferenceDetailSerializer,
    )
    @action(detail=True, methods=['post'])
    def change_status(self, request, pk=None):
        """Change conference status (organisers only)."""
        conference = self.get_object()
        new_status = request.data.get('status')

        if new_status not in dict(Conference.STATUS_CHOICES):
            return Response(
                {'error': 'Invalid status'},
                status=status.HTTP_400_BAD_REQUEST
            )

        conference.status = new_status
        conference.save()

        serializer = self.get_serializer(conference)
        return Response(serializer.data)

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    @action(detail=True, methods=['get'])
    def statistics(self, request, pk=None):
        """Get conference statistics."""
        conference = self.get_object()

        stats = {
            'total_tracks': conference.tracks.filter(is_active=True).count(),
            'total_participants': conference.current_participants,
            'available_spots': conference.get_available_spots(),
            'is_open_for_submissions': conference.is_open_for_submissions(),
            'is_open_for_registration': conference.is_open_for_registration(),
            'days_until_start': (conference.start_date - timezone.now()).days if conference.start_date > timezone.now() else 0,
        }

        return Response(stats)

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    @action(detail=True, methods=['get'])
    def personnel(self, request, pk=None):
        """
        Return everyone involved in this conference, grouped by role.

        Groups:
          - organiser
          - roles (track_chair, reviewer, keynote_speaker, sponsor, etc. from ConferenceRole)
          - authors (users who have submitted to this conference)
          - participants (approved/checked-in registrations)
        """
        conference = self.get_object()

        def user_info(user):
            return {
                'id': str(user.id),
                'email': user.email,
                'name': user.get_full_name() or user.email,
            }

        # Organiser
        organiser_data = user_info(conference.organiser)

        # ConferenceRole groups (all except organiser role, which is shown above)
        from collections import defaultdict
        role_groups = defaultdict(list)
        roles_qs = (
            ConferenceRole.objects
            .filter(conference=conference, is_active=True)
            .exclude(role='organiser')
            .select_related('user', 'track')
        )
        for cr in roles_qs:
            entry = user_info(cr.user)
            if cr.track:
                entry['track'] = cr.track.name
            role_groups[cr.role].append(entry)

        # Authors — any user who submitted to this conference
        from apps.submissions.models import Submission, SubmissionAuthor
        author_users = (
            SubmissionAuthor.objects
            .filter(submission__conference=conference)
            .select_related('user')
            .values('user__id', 'user__email', 'user__first_name', 'user__last_name',
                    'name', 'email')
            .distinct()
        )
        authors = []
        seen_author_emails = set()
        for a in author_users:
            email = a['user__email'] if a['user__email'] else a['email']
            if email in seen_author_emails:
                continue
            seen_author_emails.add(email)
            authors.append({
                'id': str(a['user__id']) if a['user__id'] else None,
                'email': email,
                'name': (
                    f"{a['user__first_name']} {a['user__last_name']}".strip()
                    if a['user__first_name']
                    else a['name']
                ),
            })

        # Participants — approved or checked-in registrations
        from apps.registrations.models import Registration
        participants_qs = (
            Registration.objects
            .filter(conference=conference, status__in=('approved', 'waitlisted', 'checked_in'))
            .select_related('participant')
        )
        participants = []
        for reg in participants_qs:
            entry = user_info(reg.participant)
            entry['ticket_type'] = reg.get_ticket_type_display()
            entry['status'] = reg.status
            participants.append(entry)

        result = {
            'conference': conference.short_name,
            'organiser': organiser_data,
            'authors': authors,
            'participants': participants,
        }
        result.update(dict(role_groups))  # track_chair, reviewer, keynote_speaker, etc. as top-level keys

        return Response(result)


class ConferenceTrackViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing conference tracks.
    """

    queryset = ConferenceTrack.objects.all()
    serializer_class = ConferenceTrackSerializer
    permission_classes = [IsAuthenticated, CanManageConference]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['conference', 'is_active', 'chair']
    search_fields = ['name', 'description', 'short_name']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or user.is_admin:
            return ConferenceTrack.objects.all()
        return ConferenceTrack.objects.filter(
            models.Q(conference__organiser=user) |
            models.Q(
                conference__user_roles__user=user,
                conference__user_roles__is_active=True
            )
        ).distinct()

    def perform_create(self, serializer):
        """Ensure track belongs to a conference the user can manage."""
        from rest_framework.exceptions import PermissionDenied
        conference = serializer.validated_data['conference']
        if not CanManageConference().has_object_permission(self.request, self, conference):
            raise PermissionDenied("You do not have permission to create a track for this conference.")
        track = serializer.save()
        self._assign_chair_role(track, assigned_by=self.request.user)
        self._notify_chair(track, is_new=True)

    def perform_update(self, serializer):
        old_chair = serializer.instance.chair
        track = serializer.save()
        new_chair = track.chair
        if new_chair and new_chair != old_chair:
            # Deactivate old chair's track_chair role for this track (if any)
            if old_chair:
                ConferenceRole.objects.filter(
                    conference=track.conference,
                    user=old_chair,
                    role='track_chair',
                    track=track,
                ).update(is_active=False)
            self._assign_chair_role(track, assigned_by=self.request.user)
            self._notify_chair(track, is_new=False)

    def _assign_chair_role(self, track, assigned_by):
        """Create or reactivate a ConferenceRole(track_chair) for the track chair."""
        if not track.chair:
            return
        ConferenceRole.objects.update_or_create(
            conference=track.conference,
            user=track.chair,
            role='track_chair',
            track=track,
            defaults={'is_active': True, 'assigned_by': assigned_by},
        )

    def _notify_chair(self, track, is_new):
        """Send in-app + email notification to the track chair.
        Only fires once the conference is open — avoids premature notifications during setup."""
        if not track.chair:
            return
        if track.conference.status != 'open':
            return
        from apps.communications.notification_service import notification_service
        conference = track.conference
        if is_new:
            title = f'Track Chair Assignment: {track.name}'
            message = (
                f'You have been assigned as chair of the "{track.name}" track '
                f'at {conference.title}. Please log in to review your responsibilities.'
            )
        else:
            title = f'Track Chair Update: {track.name}'
            message = (
                f'Your chair assignment for the "{track.name}" track '
                f'at {conference.title} has been updated.'
            )
        notification_service.create_notification(
            recipient=track.chair,
            notification_type='role_assigned',
            title=title,
            message=message,
            priority='high',
            related_object=track,
            send_email=True,
        )


class ConferenceDeadlineViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing conference deadlines.
    """

    queryset = ConferenceDeadline.objects.all()
    serializer_class = ConferenceDeadlineSerializer
    permission_classes = [IsAuthenticated, IsConferenceOrganiserOrAdmin]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['conference', 'deadline_type', 'is_active']
    ordering_fields = ['deadline_date', 'deadline_type']
    ordering = ['deadline_date']

    def get_queryset(self):
        # If user is admin/superuser, return all deadlines
        if self.request.user.is_superuser or self.request.user.is_admin:
            return ConferenceDeadline.objects.all()
        
        return (ConferenceDeadline.objects.filter(
            conference__organiser=self.request.user
        ) | ConferenceDeadline.objects.filter(
            conference__user_roles__user=self.request.user,
            conference__user_roles__role='organiser',
            conference__user_roles__is_active=True
        )).distinct()


class ConferenceRoleViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing conference user roles.
    """

    queryset = ConferenceRole.objects.all()
    serializer_class = ConferenceRoleSerializer
    permission_classes = [IsAuthenticated, IsConferenceOrganiserOrAdmin]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['conference', 'role', 'is_active', 'track']
    search_fields = ['user__first_name', 'user__last_name', 'user__email']
    ordering_fields = ['role', 'assigned_at', 'user__last_name']
    ordering = ['role', 'user__last_name']

    def get_queryset(self):
        # If user is admin/superuser, return all roles
        if self.request.user.is_superuser or self.request.user.is_admin:
            return ConferenceRole.objects.all()
        
        return (ConferenceRole.objects.filter(
            conference__organiser=self.request.user
        ) | ConferenceRole.objects.filter(
            conference__user_roles__user=self.request.user,
            conference__user_roles__role='organiser',
            conference__user_roles__is_active=True
        )).distinct()

    def perform_create(self, serializer):
        """Set assigned_by when creating roles."""
        serializer.save(assigned_by=self.request.user)


class ReviewRubricViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing review rubrics.
    """

    queryset = ReviewRubric.objects.all()
    serializer_class = ReviewRubricSerializer
    permission_classes = [IsAuthenticated, IsConferenceOrganiserOrAdmin]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['conference', 'is_default', 'is_active']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['-is_default', 'name']

    def get_queryset(self):
        # If user is admin/superuser, return all rubrics
        if self.request.user.is_superuser or self.request.user.is_admin:
            return ReviewRubric.objects.all()
        
        return (ReviewRubric.objects.filter(
            conference__organiser=self.request.user
        ) | ReviewRubric.objects.filter(
            conference__user_roles__user=self.request.user,
            conference__user_roles__role='organiser',
            conference__user_roles__is_active=True
        )).distinct()

    @extend_schema(request=None, responses=ReviewRubricSerializer)
    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        """Set this rubric as the default for the conference."""
        rubric = self.get_object()

        # Remove default from other rubrics in the same conference
        ReviewRubric.objects.filter(
            conference=rubric.conference,
            is_default=True
        ).update(is_default=False)

        # Set this one as default
        rubric.is_default = True
        rubric.save()

        serializer = self.get_serializer(rubric)
        return Response(serializer.data)


class ConferenceMediaViewSet(viewsets.ModelViewSet):
    """
    ViewSet for conference media management.
    Handles media uploads, display, and management.
    """

    queryset = ConferenceMedia.objects.all()
    serializer_class = ConferenceMediaSerializer
    permission_classes = [IsAuthenticated, CanManageConference]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['mediatype', 'is_featured', 'is_active', 'uploaded_by', 'conference']
    search_fields = ['title', 'description', 'alt_text']
    ordering_fields = ['display_order', 'uploaded_at', 'title']
    ordering = ['display_order', 'uploaded_at']

    def get_queryset(self):
        """Filter media by conference."""
        conference_id = self.request.query_params.get('conference')
        if conference_id:
            return ConferenceMedia.objects.filter(conference_id=conference_id)
        return ConferenceMedia.objects.all()

    def get_serializer_class(self):
        """Use upload serializer for create and upload actions."""
        if self.action in ['create', 'upload']:
            return ConferenceMediaUploadSerializer
        return ConferenceMediaSerializer

    @extend_schema(
        request={'multipart/form-data': ConferenceMediaUploadSerializer},
        responses={201: ConferenceMediaSerializer},
    )
    def create(self, request, *args, **kwargs):
        """Create a conference media record with file upload."""
        serializer = ConferenceMediaUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        conference = get_object_or_404(Conference, id=serializer.validated_data['conference'])

        if not CanManageConference().has_object_permission(request, self, conference):
            return Response(
                {"error": "You don't have permission to upload media for this conference."},
                status=status.HTTP_403_FORBIDDEN
            )

        file_obj = serializer.validated_data['file']
        from apps.core.utils import upload_file_to_cloudinary

        try:
            upload_result = upload_file_to_cloudinary(
                file_obj,
                folder=f'conferences/{conference.short_name}/media'
            )

            media = ConferenceMedia.objects.create(
                conference=conference,
                name=serializer.validated_data['name'],
                mediatype=serializer.validated_data['mediatype'],
                title=serializer.validated_data['title'],
                description=serializer.validated_data.get('description', ''),
                alt_text=serializer.validated_data.get('alt_text', ''),
                file_url=upload_result['url'],
                public_id=upload_result['public_id'],
                service='cloudinary',
                file_size=file_obj.size,
                mime_type=file_obj.content_type,
                width=upload_result.get('width'),
                height=upload_result.get('height'),
                is_featured=serializer.validated_data.get('is_featured', False),
                display_order=serializer.validated_data.get('display_order', 0),
                uploaded_by=request.user,
            )

            return Response(ConferenceMediaSerializer(media).data, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response(
                {"error": f"Failed to upload file: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def perform_create(self, serializer):
        """Set the conference and uploaded_by when creating media."""
        conference_id = self.request.data.get('conference')
        if conference_id:
            conference = get_object_or_404(Conference, id=conference_id)
            serializer.save(
                conference=conference,
                uploaded_by=self.request.user,
            )
        else:
            serializer.save(uploaded_by=self.request.user)

    @extend_schema(
        request={'multipart/form-data': ConferenceMediaUploadSerializer},
        responses={201: ConferenceMediaSerializer},
    )
    @action(detail=False, methods=['post'])
    def upload(self, request):
        """
        Upload media file for a conference.
        """
        serializer = ConferenceMediaUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        conference = get_object_or_404(Conference, id=serializer.validated_data['conference'])

        # Check permissions
        if not CanManageConference().has_object_permission(request, self, conference):
            return Response(
                {"error": "You don't have permission to upload media for this conference."},
                status=status.HTTP_403_FORBIDDEN
            )

        file_obj = serializer.validated_data['file']

        from apps.core.utils import upload_file_to_cloudinary
        try:
            upload_result = upload_file_to_cloudinary(
                file_obj,
                folder=f'conferences/{conference.short_name}/media'
            )

            media = ConferenceMedia.objects.create(
                conference=conference,
                name=serializer.validated_data['name'],
                mediatype=serializer.validated_data['mediatype'],
                title=serializer.validated_data['title'],
                description=serializer.validated_data.get('description', ''),
                alt_text=serializer.validated_data.get('alt_text', ''),
                file_url=upload_result['url'],
                public_id=upload_result['public_id'],
                service='cloudinary',
                file_size=file_obj.size,
                mime_type=file_obj.content_type,
                width=upload_result.get('width'),
                height=upload_result.get('height'),
                is_featured=serializer.validated_data.get('is_featured', False),
                display_order=serializer.validated_data.get('display_order', 0),
                uploaded_by=request.user,
            )

            return Response(ConferenceMediaSerializer(media).data, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response(
                {"error": f"Failed to upload file: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @extend_schema(request=None, responses=ConferenceMediaSerializer)
    @action(detail=True, methods=['post'])
    def set_featured(self, request, pk=None):
        """
        Set media as featured (for banners).
        """
        media = self.get_object()
        conference = media.conference

        # Check permissions
        if not IsConferenceOrganiserOrAdmin().has_object_permission(request, self, conference):
            return Response(
                {"error": "Only conference organisers can set featured media."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Unset other featured banners of same type
        ConferenceMedia.objects.filter(
            conference=conference,
            name='banner',
            is_featured=True
        ).exclude(id=media.id).update(is_featured=False)

        # Set this one as featured
        media.is_featured = True
        media.save(update_fields=['is_featured'])

        serializer = self.get_serializer(media)
        return Response(serializer.data)

    @extend_schema(request=None, responses={204: None})
    @action(detail=True, methods=['delete'])
    def delete_media(self, request, pk=None):
        """
        Delete media file and cloud storage.
        """
        media = self.get_object()
        conference = media.conference

        # Check permissions
        if not CanManageConference().has_object_permission(request, self, conference):
            return Response(
                {"error": "You don't have permission to delete this media."},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            # Delete from cloud storage
            from apps.core.utils import delete_file_from_cloudinary
            delete_file_from_cloudinary(media.public_id)

            # Delete record
            media.delete()

            return Response(
                {"message": "Media deleted successfully."},
                status=status.HTTP_204_NO_CONTENT
            )

        except Exception as e:
            return Response(
                {"error": f"Failed to delete media: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )