"""ViewSets for the Scheduling app."""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from django.core.cache import cache
from django.conf import settings
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes

from apps.scheduling.models import Session, SessionPresentation
from apps.scheduling.services import SchedulingService
from apps.scheduling.serializers import (
    SessionListSerializer, SessionDetailSerializer,
    SessionCreateSerializer, SessionUpdateSerializer,
    SessionCancelSerializer,
    SessionPresentationSerializer, SessionPresentationCreateSerializer,
    SessionPresentationUpdateSerializer,
)


class SessionViewSet(viewsets.GenericViewSet):
    """
    Conference session / programme management.

    list            GET    /sessions/
    retrieve        GET    /sessions/{id}/
    create          POST   /sessions/              (organiser)
    partial_update  PATCH  /sessions/{id}/         (organiser)
    destroy         DELETE /sessions/{id}/         (organiser)
    publish         POST   /sessions/{id}/publish/ (organiser)
    programme       GET    /sessions/programme/?conference={id}
    presentations   GET    /sessions/{id}/presentations/
    add_presentation POST  /sessions/{id}/presentations/
    remove_presentation DELETE /sessions/{id}/presentations/{pres_id}/
    """
    queryset = Session.objects.all()
    serializer_class = SessionDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Session.objects.select_related(
            'conference', 'track', 'chair'
        ).prefetch_related('presentations__submission')

        # Public view: published sessions for any conference
        # Organiser view: all sessions for their conferences
        if user.is_admin or user.is_superuser:
            pass
        elif user.is_organiser:
            qs = qs.filter(conference__organiser=user)
        else:
            qs = qs.filter(status='published', is_public=True)

        # Filters
        conference = self.request.query_params.get('conference')
        if conference:
            qs = qs.filter(conference=conference)

        track = self.request.query_params.get('track')
        if track:
            qs = qs.filter(track=track)

        session_type = self.request.query_params.get('type')
        if session_type:
            qs = qs.filter(session_type=session_type)

        date = self.request.query_params.get('date')
        if date:
            qs = qs.filter(start_time__date=date)

        return qs

    @extend_schema(
        parameters=[
            OpenApiParameter('conference', OpenApiTypes.UUID, description='Filter by conference ID'),
            OpenApiParameter('track', OpenApiTypes.UUID, description='Filter by track ID'),
            OpenApiParameter('type', OpenApiTypes.STR, description='Filter by session type'),
            OpenApiParameter('date', OpenApiTypes.DATE, description='Filter by date (YYYY-MM-DD)'),
        ],
        responses=SessionListSerializer(many=True),
    )
    def list(self, request):
        qs = self.get_queryset()
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(SessionListSerializer(page, many=True).data)
        return Response(SessionListSerializer(qs, many=True).data)

    @extend_schema(responses=SessionDetailSerializer)
    def retrieve(self, request, pk=None):
        session = get_object_or_404(self.get_queryset(), pk=pk)
        return Response(SessionDetailSerializer(session).data)

    @extend_schema(request=SessionCreateSerializer, responses={201: SessionDetailSerializer})
    def create(self, request):
        self._require_organiser()
        serializer = SessionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self._check_conference_ownership(serializer.validated_data['conference'])

        try:
            session = SchedulingService.create_session(request.user, serializer.validated_data)
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(SessionDetailSerializer(session).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=SessionUpdateSerializer, responses=SessionDetailSerializer)
    def partial_update(self, request, pk=None):
        self._require_organiser()
        session = self._get_organiser_session(pk)
        serializer = SessionUpdateSerializer(session, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        try:
            session = SchedulingService.update_session(request.user, session, serializer.validated_data)
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        cache.delete(f'programme:{session.conference_id}')
        return Response(SessionDetailSerializer(session).data)

    def destroy(self, request, pk=None):
        self._require_organiser()
        session = self._get_organiser_session(pk)
        conference_id = session.conference_id
        from apps.audit.models import AuditLogManager
        AuditLogManager.log(
            action='schedule.session.deleted',
            actor=request.user,
            obj=session,
            new_values={'title': session.title},
        )
        session.delete()
        cache.delete(f'programme:{conference_id}')
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=None, responses=SessionDetailSerializer)
    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        """Publish a session to the public programme."""
        self._require_organiser()
        session = self._get_organiser_session(pk)
        try:
            session = SchedulingService.publish_session(request.user, session)
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        cache.delete(f'programme:{session.conference_id}')
        return Response(SessionDetailSerializer(session).data)

    @extend_schema(request=SessionCancelSerializer, responses={200: SessionDetailSerializer})
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a session and notify all assigned presenters."""
        self._require_organiser()
        session = self._get_organiser_session(pk)
        serializer = SessionCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            session = SchedulingService.cancel_session(
                request.user, session, reason=serializer.validated_data.get('reason', '')
            )
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        cache.delete(f'programme:{session.conference_id}')
        return Response(SessionDetailSerializer(session).data)

    @extend_schema(
        parameters=[OpenApiParameter('conference', OpenApiTypes.UUID, required=True, description='Conference ID')],
        responses={200: OpenApiTypes.OBJECT},
        description='Full conference programme — all published sessions grouped by date.',
    )
    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def programme(self, request):
        """
        Full conference programme — all published sessions grouped by date.
        Public endpoint (no auth required for published conferences).
        """
        conference_id = request.query_params.get('conference')
        if not conference_id:
            return Response(
                {'detail': 'conference query param is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        cache_key = f'programme:{conference_id}'
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        qs = Session.objects.filter(
            conference=conference_id,
            status='published',
            is_public=True,
        ).select_related('track', 'chair').prefetch_related(
            'presentations__submission__submitted_by'
        ).order_by('start_time', 'order')

        from collections import defaultdict
        grouped = defaultdict(list)
        for session in qs:
            day = session.start_time.date().isoformat()
            grouped[day].append(SessionDetailSerializer(session).data)

        result = {
            'conference': conference_id,
            'days': [
                {'date': day, 'sessions': sessions}
                for day, sessions in sorted(grouped.items())
            ]
        }
        timeout = getattr(settings, 'CACHE_TIMEOUT_PROGRAMME', 600)
        cache.set(cache_key, result, timeout)
        return Response(result)

    # ── Presentations sub-resource ─────────────────────────────────────────────

    @extend_schema(methods=['get'], responses=SessionPresentationSerializer(many=True))
    @extend_schema(methods=['post'], request=SessionPresentationCreateSerializer, responses={201: SessionPresentationSerializer})
    @action(detail=True, methods=['get', 'post'], url_path='presentations')
    def presentations(self, request, pk=None):
        session = get_object_or_404(self.get_queryset(), pk=pk)

        if request.method == 'GET':
            return Response(
                SessionPresentationSerializer(session.presentations.all(), many=True).data
            )

        # POST — organiser only
        self._require_organiser()
        self._check_conference_ownership(session.conference)

        serializer = SessionPresentationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            presentation = SchedulingService.assign_presentation(
                request.user, session, serializer.validated_data
            )
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        cache.delete(f'programme:{session.conference_id}')
        return Response(
            SessionPresentationSerializer(presentation).data,
            status=status.HTTP_201_CREATED
        )

    @extend_schema(
        parameters=[OpenApiParameter('pres_id', OpenApiTypes.UUID, OpenApiParameter.PATH, description='Presentation ID')],
        request=SessionPresentationUpdateSerializer,
        responses=SessionPresentationSerializer,
    )
    @action(
        detail=True, methods=['patch'],
        url_path=r'presentations/(?P<pres_id>[^/.]+)/update'
    )
    def update_presentation(self, request, pk=None, pres_id=None):
        """Update presentation details (timing, confirmation, order, speaker info)."""
        self._require_organiser()
        session = self._get_organiser_session(pk)
        presentation = get_object_or_404(SessionPresentation, pk=pres_id, session=session)
        serializer = SessionPresentationUpdateSerializer(
            presentation, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        presentation = SchedulingService.update_presentation(
            request.user, presentation, serializer.validated_data
        )
        cache.delete(f'programme:{session.conference_id}')
        return Response(SessionPresentationSerializer(presentation).data)

    @extend_schema(
        parameters=[OpenApiParameter('pres_id', OpenApiTypes.UUID, OpenApiParameter.PATH, description='Presentation ID')],
        responses={200: SessionPresentationSerializer},
        description='Presenter confirms or declines their scheduled slot.',
    )
    @action(
        detail=True, methods=['post'],
        url_path=r'presentations/(?P<pres_id>[^/.]+)/confirm'
    )
    def confirm_presentation(self, request, pk=None, pres_id=None):
        """
        Presenter confirms (or declines) their scheduled slot.
        The presenter must be the submission author or the linked speaker_user.
        Organisers can also call this to confirm on behalf.
        """
        print(f"Confirming presentation {pres_id} in session {pk} by user {request.user}")
        # session = get_object_or_404(self.get_queryset(), pk=pk)
        session = Session.objects.filter(pk=pk).select_related('conference').first()  # Check session exists and is accessible
        if not session:
            return Response({'detail': 'Session not found.'}, status=status.HTTP_404_NOT_FOUND)
        presentation = get_object_or_404(SessionPresentation, pk=pres_id, session=session)

        user = request.user
        is_organiser = user.is_organiser or user.is_admin

        # Check the caller is the presenter or the organiser
        is_presenter = (
            (presentation.speaker_user and presentation.speaker_user == user) or
            (presentation.submission and presentation.submission.submitted_by == user)
        )

        if not is_organiser and not is_presenter:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(
                "Only the presenter or the organiser can confirm this slot."
            )

        confirmed = request.data.get('confirmed', True)
        if not isinstance(confirmed, bool):
            return Response(
                {'detail': '`confirmed` must be a boolean.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        presentation.is_confirmed = confirmed
        presentation.save(update_fields=['is_confirmed'])

        # Notify organiser when presenter self-confirms or declines
        if is_presenter:
            from apps.communications.notification_service import notification_service
            action_word = 'confirmed' if confirmed else 'declined'
            notification_service.create_notification(
                recipient=session.conference.organiser,
                notification_type='system',
                title=f'Presenter {action_word.capitalize()}: {presentation.get_title()}',
                message=(
                    f'{user.get_full_name() or user.email} has {action_word} their presentation '
                    f'slot in "{session.title}".'
                ),
                priority='medium',
                related_object=presentation,
                send_email=False,
            )

        cache.delete(f'programme:{session.conference_id}')
        return Response(SessionPresentationSerializer(presentation).data)

    @extend_schema(
        parameters=[OpenApiParameter('pres_id', OpenApiTypes.UUID, OpenApiParameter.PATH, description='Presentation ID')],
        responses={204: None},
    )
    @action(
        detail=True, methods=['delete'],
        url_path=r'presentations/(?P<pres_id>[^/.]+)'
    )
    def remove_presentation(self, request, pk=None, pres_id=None):
        self._require_organiser()
        session = self._get_organiser_session(pk)
        presentation = get_object_or_404(SessionPresentation, pk=pres_id, session=session)
        SchedulingService.remove_presentation(request.user, presentation)
        cache.delete(f'programme:{session.conference_id}')
        return Response(status=status.HTTP_204_NO_CONTENT)

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _require_organiser(self):
        if not (self.request.user.is_organiser or self.request.user.is_admin):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only organisers can manage sessions.")

    def _check_conference_ownership(self, conference):
        if not (self.request.user.is_admin or conference.organiser == self.request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You are not the organiser of this conference.")

    def _get_organiser_session(self, pk):
        user = self.request.user
        qs = Session.objects.select_related('conference')
        if not (user.is_admin or user.is_superuser):
            qs = qs.filter(conference__organiser=user)
        return get_object_or_404(qs, pk=pk)
