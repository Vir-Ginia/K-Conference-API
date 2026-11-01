"""ViewSets for the Submissions app."""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes

from apps.submissions.models import Submission, SubmissionAuthor, SubmissionFile, SubmissionVersion
from apps.submissions.services import SubmissionService
from apps.submissions.permissions import IsSubmissionOwner, CanViewSubmission, IsConferenceOrganiserForSubmission
from apps.submissions.serializers import (
    SubmissionListSerializer,
    SubmissionDetailSerializer,
    SubmissionCreateSerializer,
    SubmissionUpdateSerializer,
    SubmissionOverrideSerializer,
    SubmissionAuthorSerializer,
    SubmissionFileSerializer,
    SubmissionVersionSerializer,
)

_SUBMISSION_FILTERS = [
    OpenApiParameter('conference', OpenApiTypes.UUID, description='Filter by conference ID'),
    OpenApiParameter('track', OpenApiTypes.UUID, description='Filter by track ID'),
    OpenApiParameter('status', OpenApiTypes.STR, description='Filter by status (draft, submitted, under_review, accepted, rejected, withdrawn)'),
]


class SubmissionViewSet(viewsets.GenericViewSet):
    """
    Conference paper submission management.

    list            GET    /submissions/
    retrieve        GET    /submissions/{id}/
    create          POST   /submissions/                  (multipart)
    partial_update  PATCH  /submissions/{id}/             (multipart)
    submit          POST   /submissions/{id}/submit/
    withdraw        POST   /submissions/{id}/withdraw/
    override        POST   /submissions/{id}/override/    (organiser only, multipart)
    authors         GET    /submissions/{id}/authors/
    add_author      POST   /submissions/{id}/authors/
    remove_author   DELETE /submissions/{id}/authors/{author_id}/
    files           GET    /submissions/{id}/files/
    versions        GET    /submissions/{id}/versions/
    """
    queryset = Submission.objects.all()
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Submission.objects.select_related(
            'conference', 'track', 'submitted_by'
        ).prefetch_related('authors', 'files')

        # Admins and superusers see everything
        if user.is_admin or user.is_superuser:
            pass
        # Organisers see all submissions for their conferences
        elif user.is_organiser:
            qs = qs.filter(conference__organiser=user)
        # Authors see only their own
        else:
            qs = qs.filter(submitted_by=user)

        # Optional filters
        conference = self.request.query_params.get('conference')
        if conference:
            qs = qs.filter(conference=conference)

        track = self.request.query_params.get('track')
        if track:
            qs = qs.filter(track=track)

        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return SubmissionListSerializer
        if self.action == 'create':
            return SubmissionCreateSerializer
        if self.action == 'partial_update':
            return SubmissionUpdateSerializer
        if self.action == 'override':
            return SubmissionOverrideSerializer
        return SubmissionDetailSerializer

    # ── CRUD ──────────────────────────────────────────────────────────────────

    @extend_schema(
        parameters=_SUBMISSION_FILTERS,
        responses=SubmissionListSerializer(many=True),
    )
    def list(self, request):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @extend_schema(responses=SubmissionDetailSerializer)
    def retrieve(self, request, pk=None):
        submission = self._get_submission(pk)
        self.check_object_permissions(request, submission)
        serializer = SubmissionDetailSerializer(submission)
        return Response(serializer.data)

    @extend_schema(
        request={'multipart/form-data': SubmissionCreateSerializer},
        responses={201: SubmissionDetailSerializer},
    )
    def create(self, request):
        if not request.user.is_author:
            return Response(
                {'detail': 'Only users with the Author role can submit papers.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = SubmissionCreateSerializer(
            data=request.data, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)

        file = serializer.validated_data.pop('file', None)
        try:
            submission = SubmissionService.create_submission(
                user=request.user,
                validated_data=serializer.validated_data,
                file=file,
            )
        except (PermissionError, ValueError) as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            SubmissionDetailSerializer(submission).data,
            status=status.HTTP_201_CREATED
        )

    @extend_schema(
        request={'multipart/form-data': SubmissionUpdateSerializer},
        responses=SubmissionDetailSerializer,
    )
    def partial_update(self, request, pk=None):
        submission = self._get_submission(pk)
        self.check_object_permissions(request, submission)

        # Enforce ownership
        if submission.submitted_by != request.user and not request.user.is_admin:
            return Response(
                {'detail': 'You do not have permission to edit this submission.'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = SubmissionUpdateSerializer(
            submission, data=request.data, partial=True, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        file = serializer.validated_data.pop('file', None)

        try:
            submission = SubmissionService.update_submission(
                user=request.user,
                submission=submission,
                validated_data=serializer.validated_data,
                file=file,
            )
        except (PermissionError, ValueError) as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(SubmissionDetailSerializer(submission).data)

    # ── Actions ───────────────────────────────────────────────────────────────

    @extend_schema(request=None, responses=SubmissionDetailSerializer)
    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """Move a draft submission to 'submitted' status."""
        submission = self._get_submission(pk)
        if submission.submitted_by != request.user:
            return Response(
                {'detail': 'Only the submitting author can submit this paper.'},
                status=status.HTTP_403_FORBIDDEN
            )
        try:
            submission = SubmissionService.submit_submission(request.user, submission)
        except (PermissionError, ValueError) as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(SubmissionDetailSerializer(submission).data)

    @extend_schema(request=None, responses=SubmissionDetailSerializer)
    @action(detail=True, methods=['post'])
    def withdraw(self, request, pk=None):
        """Withdraw a submission."""
        submission = self._get_submission(pk)
        if submission.submitted_by != request.user and not request.user.is_admin:
            return Response(
                {'detail': 'Only the submitting author can withdraw this paper.'},
                status=status.HTTP_403_FORBIDDEN
            )
        try:
            submission = SubmissionService.withdraw_submission(request.user, submission)
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(SubmissionDetailSerializer(submission).data)

    @extend_schema(
        request={'multipart/form-data': SubmissionOverrideSerializer},
        responses=SubmissionDetailSerializer,
    )
    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser, JSONParser])
    def override(self, request, pk=None):
        """Organiser override: edit a locked submission with mandatory reason."""
        submission = self._get_submission(pk)
        self._require_organiser(submission)

        serializer = SubmissionOverrideSerializer(
            data=request.data, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)

        reason = serializer.validated_data.pop('reason')
        file = serializer.validated_data.pop('file', None)

        try:
            submission = SubmissionService.organiser_override(
                organiser=request.user,
                submission=submission,
                validated_data=serializer.validated_data,
                reason=reason,
                file=file,
            )
        except (PermissionError, ValueError) as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(SubmissionDetailSerializer(submission).data)

    # ── Authors sub-resource ─────────────────────────────────────────────────

    @extend_schema(methods=['get'], responses=SubmissionAuthorSerializer(many=True))
    @extend_schema(methods=['post'], request=SubmissionAuthorSerializer, responses={201: SubmissionAuthorSerializer})
    @action(detail=True, methods=['get', 'post'], url_path='authors')
    def authors(self, request, pk=None):
        submission = self._get_submission(pk)

        if request.method == 'GET':
            serializer = SubmissionAuthorSerializer(
                submission.authors.all(), many=True
            )
            return Response(serializer.data)

        # POST — add co-author (owner or organiser only)
        if submission.submitted_by != request.user and not request.user.is_admin:
            if submission.conference.organiser != request.user:
                return Response(
                    {'detail': 'You do not have permission to add authors.'},
                    status=status.HTTP_403_FORBIDDEN
                )
        if not submission.is_editable:
            return Response(
                {'detail': 'Submission is locked. Use organiser override to make changes.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        serializer = SubmissionAuthorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from apps.accounts.models import User as UserModel
        matched_user = UserModel.objects.filter(
            email=serializer.validated_data['email']
        ).first()
        author = serializer.save(submission=submission, user=matched_user)
        return Response(
            SubmissionAuthorSerializer(author).data,
            status=status.HTTP_201_CREATED
        )

    @extend_schema(
        parameters=[OpenApiParameter('author_id', OpenApiTypes.UUID, OpenApiParameter.PATH, description='ID of the author to remove')],
        responses={204: None},
    )
    @action(detail=True, methods=['delete'], url_path=r'authors/(?P<author_id>[^/.]+)')
    def remove_author(self, request, pk=None, author_id=None):
        """Remove a co-author. Cannot remove the primary author."""
        submission = self._get_submission(pk)
        if submission.submitted_by != request.user and not request.user.is_admin:
            return Response(
                {'detail': 'You do not have permission to remove authors.'},
                status=status.HTTP_403_FORBIDDEN
            )
        try:
            author = submission.authors.get(id=author_id)
        except SubmissionAuthor.DoesNotExist:
            return Response({'detail': 'Author not found.'}, status=status.HTTP_404_NOT_FOUND)

        if author.is_primary:
            return Response(
                {'detail': 'Cannot remove the primary author.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        author.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # ── Files sub-resource ────────────────────────────────────────────────────

    @extend_schema(responses=SubmissionFileSerializer(many=True))
    @action(detail=True, methods=['get'], url_path='files')
    def files(self, request, pk=None):
        """List all files for a submission (current and historical)."""
        submission = self._get_submission(pk)
        self.check_object_permissions(request, submission)
        files = submission.files.all()
        return Response(SubmissionFileSerializer(files, many=True).data)

    # ── Version history ───────────────────────────────────────────────────────

    @extend_schema(responses=SubmissionVersionSerializer(many=True))
    @action(detail=True, methods=['get'], url_path='versions')
    def versions(self, request, pk=None):
        """List organiser-override version history for a submission."""
        submission = self._get_submission(pk)
        self.check_object_permissions(request, submission)
        versions = submission.versions.all()
        return Response(SubmissionVersionSerializer(versions, many=True).data)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_submission(self, pk):
        from django.shortcuts import get_object_or_404
        return get_object_or_404(
            Submission.objects.select_related(
                'conference', 'track', 'submitted_by', 'deadline_override_by'
            ).prefetch_related('authors', 'files', 'versions'),
            pk=pk
        )

    def _require_organiser(self, submission):
        user = self.request.user
        if not (user.is_admin or submission.conference.organiser == user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(
                "Only the conference organiser can perform this action."
            )
