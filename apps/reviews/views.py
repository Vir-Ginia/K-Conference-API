"""ViewSets for the Reviews app."""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes

from apps.submissions.models import Submission
from apps.reviews.models import ReviewAssignment, ConflictOfInterest, Review, ReviewDecision
from apps.reviews.services import ReviewService
from apps.reviews.serializers import (
    ReviewAssignmentListSerializer, ReviewAssignmentCreateSerializer,
    ConflictOfInterestSerializer, ConflictOfInterestCreateSerializer,
    ReviewListSerializer, ReviewDetailSerializer,
    ReviewDraftSerializer, ReviewOverrideSerializer,
    ReviewDecisionSerializer, ReviewDecisionCreateSerializer, PublishDecisionSerializer,
)


class ReviewAssignmentViewSet(viewsets.GenericViewSet):
    """
    Manage reviewer assignments.

    list        GET  /assignments/
    retrieve    GET  /assignments/{id}/
    create      POST /assignments/                   (organiser only)
    destroy     DELETE /assignments/{id}/            (organiser only)
    accept      POST /assignments/{id}/accept/       (reviewer)
    decline     POST /assignments/{id}/decline/      (reviewer)
    progress    GET  /assignments/progress/?conference={id}  (organiser)
    """
    queryset = ReviewAssignment.objects.all()
    serializer_class = ReviewAssignmentListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = ReviewAssignment.objects.select_related(
            'submission__conference', 'reviewer', 'assigned_by'
        )
        if user.is_admin or user.is_superuser:
            pass
        elif user.is_organiser:
            qs = qs.filter(submission__conference__organiser=user)
        else:
            qs = qs.filter(reviewer=user)

        # Optional filters
        conference = self.request.query_params.get('conference')
        if conference:
            qs = qs.filter(submission__conference=conference)

        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        active_only = self.request.query_params.get('active')
        if active_only and active_only.lower() == 'true':
            qs = qs.filter(is_active=True)

        return qs

    @extend_schema(
        parameters=[
            OpenApiParameter('conference', OpenApiTypes.UUID, description='Filter by conference ID'),
            OpenApiParameter('status', OpenApiTypes.STR, description='Filter by assignment status'),
            OpenApiParameter('active', OpenApiTypes.BOOL, description='Only active assignments'),
        ],
        responses=ReviewAssignmentListSerializer(many=True),
    )
    def list(self, request):
        qs = self.get_queryset()
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(
                ReviewAssignmentListSerializer(page, many=True).data
            )
        return Response(ReviewAssignmentListSerializer(qs, many=True).data)

    def retrieve(self, request, pk=None):
        assignment = get_object_or_404(self.get_queryset(), pk=pk)
        return Response(ReviewAssignmentListSerializer(assignment).data)

    def create(self, request):
        self._require_organiser()
        serializer = ReviewAssignmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from apps.accounts.models import User
        reviewer = get_object_or_404(User, pk=serializer.validated_data['reviewer'].pk)
        submission = serializer.validated_data['submission']
        self._check_organiser_for_conference(submission.conference)

        try:
            assignment = ReviewService.assign_reviewer(
                organiser=request.user,
                submission=submission,
                reviewer=reviewer,
                due_date=serializer.validated_data.get('due_date'),
            )
        except (ValueError, PermissionError) as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            ReviewAssignmentListSerializer(assignment).data,
            status=status.HTTP_201_CREATED
        )

    def destroy(self, request, pk=None):
        self._require_organiser()
        assignment = get_object_or_404(ReviewAssignment, pk=pk)
        self._check_organiser_for_conference(assignment.submission.conference)
        ReviewService.unassign_reviewer(request.user, assignment)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=None, responses=ReviewAssignmentListSerializer)
    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        """Reviewer accepts an assignment."""
        assignment = get_object_or_404(ReviewAssignment, pk=pk, reviewer=request.user)
        try:
            assignment = ReviewService.respond_to_assignment(request.user, assignment, accept=True)
        except (ValueError, PermissionError) as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ReviewAssignmentListSerializer(assignment).data)

    @extend_schema(request=None, responses=ReviewAssignmentListSerializer)
    @action(detail=True, methods=['post'])
    def decline(self, request, pk=None):
        """Reviewer declines an assignment."""
        assignment = get_object_or_404(ReviewAssignment, pk=pk, reviewer=request.user)
        try:
            assignment = ReviewService.respond_to_assignment(request.user, assignment, accept=False)
        except (ValueError, PermissionError) as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ReviewAssignmentListSerializer(assignment).data)

    @extend_schema(request=None, responses=ReviewAssignmentListSerializer)
    @action(detail=True, methods=['post'], url_path='resend-notification')
    def resend_notification(self, request, pk=None):
        """Organiser resends the review assignment notification (in-app + email)."""
        self._require_organiser()
        assignment = get_object_or_404(ReviewAssignment, pk=pk)
        self._check_organiser_for_conference(assignment.submission.conference)

        if not assignment.is_active:
            return Response(
                {'detail': 'Cannot resend notification for an inactive assignment.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        ReviewService._notify_reviewer_assigned(assignment)
        return Response({'detail': 'Notification resent successfully.'})

    @extend_schema(
        parameters=[OpenApiParameter('conference', OpenApiTypes.UUID, required=True, description='Conference ID')],
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=['get'])
    def progress(self, request):
        """
        Organiser view: review progress per submission for a conference.
        Returns counts of total/completed/pending assignments per submission.
        """
        self._require_organiser()
        conference_id = request.query_params.get('conference')
        if not conference_id:
            return Response(
                {'detail': 'conference query param is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        qs_filter = {'submission__conference': conference_id}
        if not (request.user.is_admin or request.user.is_superuser):
            qs_filter['submission__conference__organiser'] = request.user

        assignments = ReviewAssignment.objects.filter(
            **qs_filter
        ).select_related('submission', 'reviewer')

        from collections import defaultdict
        progress = defaultdict(lambda: {
            'submission_id': None, 'submission_title': None,
            'total': 0, 'completed': 0, 'pending': 0, 'declined': 0, 'recused': 0,
        })

        for a in assignments:
            sid = str(a.submission_id)
            progress[sid]['submission_id'] = sid
            progress[sid]['submission_title'] = a.submission.title
            progress[sid]['total'] += 1
            progress[sid][a.status if a.status in ('completed', 'declined', 'recused') else 'pending'] += 1

        return Response(list(progress.values()))

    def _require_organiser(self):
        if not (self.request.user.is_organiser or self.request.user.is_admin):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only organisers can perform this action.")

    def _check_organiser_for_conference(self, conference):
        if not (self.request.user.is_admin or conference.organiser == self.request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You are not the organiser of this conference.")


class ConflictOfInterestViewSet(viewsets.GenericViewSet):
    """
    Conflict of interest declarations.

    list     GET  /conflicts/
    create   POST /conflicts/
    """
    queryset = ConflictOfInterest.objects.all()
    serializer_class = ConflictOfInterestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_admin or user.is_organiser:
            qs = ConflictOfInterest.objects.select_related('reviewer', 'submission')
            conference = self.request.query_params.get('conference')
            if conference:
                qs = qs.filter(submission__conference=conference)
            return qs
        return ConflictOfInterest.objects.filter(reviewer=user).select_related('submission')

    @extend_schema(
        parameters=[OpenApiParameter('conference', OpenApiTypes.UUID, description='Filter by conference ID')],
        responses=ConflictOfInterestSerializer(many=True),
    )
    def list(self, request):
        qs = self.get_queryset()
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(ConflictOfInterestSerializer(page, many=True).data)
        return Response(ConflictOfInterestSerializer(qs, many=True).data)

    def create(self, request):
        serializer = ConflictOfInterestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        submission = get_object_or_404(Submission, pk=serializer.validated_data['submission'])
        try:
            coi = ReviewService.declare_conflict(
                reviewer=request.user,
                submission=submission,
                reason=serializer.validated_data['reason'],
            )
        except (ValueError, PermissionError) as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            ConflictOfInterestSerializer(coi).data,
            status=status.HTTP_201_CREATED
        )

    @extend_schema(request=None, responses=ConflictOfInterestSerializer)
    @action(detail=True, methods=['post'])
    def acknowledge(self, request, pk=None):
        """Organiser acknowledges a declared COI."""
        if not (request.user.is_organiser or request.user.is_admin):
            return Response({'detail': 'Only organisers can acknowledge COIs.'}, status=status.HTTP_403_FORBIDDEN)

        from django.utils import timezone
        coi = get_object_or_404(ConflictOfInterest, pk=pk)
        coi.acknowledged_by = request.user
        coi.acknowledged_at = timezone.now()
        coi.save(update_fields=['acknowledged_by', 'acknowledged_at'])
        return Response(ConflictOfInterestSerializer(coi).data)


class ReviewViewSet(viewsets.GenericViewSet):
    """
    Reviewer portal and organiser review management.

    list            GET  /reviews/
    retrieve        GET  /reviews/{id}/
    save_draft      POST /reviews/draft/{assignment_id}/
    submit          POST /reviews/{id}/submit/
    override        POST /reviews/{id}/override/    (organiser only)
    aggregate       GET  /reviews/aggregate/?submission={id}  (organiser)
    """
    queryset = Review.objects.all()
    serializer_class = ReviewDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Review.objects.select_related(
            'submission__conference', 'reviewer', 'rubric', 'assignment'
        ).prefetch_related('scores')

        if user.is_admin or user.is_superuser:
            pass
        elif user.is_organiser:
            qs = qs.filter(submission__conference__organiser=user)
        else:
            qs = qs.filter(reviewer=user)

        conference = self.request.query_params.get('conference')
        if conference:
            qs = qs.filter(submission__conference=conference)

        submission = self.request.query_params.get('submission')
        if submission:
            qs = qs.filter(submission=submission)

        return qs

    @extend_schema(
        parameters=[
            OpenApiParameter('conference', OpenApiTypes.UUID, description='Filter by conference ID'),
            OpenApiParameter('submission', OpenApiTypes.UUID, description='Filter by submission ID'),
        ],
        responses=ReviewListSerializer(many=True),
    )
    def list(self, request):
        qs = self.get_queryset()
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(ReviewListSerializer(page, many=True).data)
        return Response(ReviewListSerializer(qs, many=True).data)

    @extend_schema(responses=ReviewDetailSerializer)
    def retrieve(self, request, pk=None):
        review = get_object_or_404(self.get_queryset(), pk=pk)
        # Hide organiser-only comments from authors/reviewers
        serializer = ReviewDetailSerializer(review)
        data = serializer.data
        if not (request.user.is_organiser or request.user.is_admin):
            data.pop('comments_to_organisers', None)
        return Response(data)

    @extend_schema(
        request=ReviewDraftSerializer,
        responses=ReviewDetailSerializer,
        parameters=[OpenApiParameter('assignment_id', OpenApiTypes.UUID, OpenApiParameter.PATH, description='Assignment ID')],
    )
    @action(detail=False, methods=['post'], url_path=r'draft/(?P<assignment_id>[^/.]+)')
    def save_draft(self, request, assignment_id=None):
        """Reviewer saves or updates a review draft."""
        assignment = get_object_or_404(
            ReviewAssignment, pk=assignment_id, reviewer=request.user, is_active=True
        )
        serializer = ReviewDraftSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        scores_data = data.pop('scores', [])

        # Resolve rubric FK if provided
        rubric = None
        if data.get('rubric'):
            from apps.conferences.models import ReviewRubric
            rubric = get_object_or_404(ReviewRubric, pk=data.pop('rubric'))
            data['rubric'] = rubric

        try:
            review = ReviewService.save_review_draft(
                reviewer=request.user,
                assignment=assignment,
                review_data=data,
                scores_data=scores_data,
            )
        except (ValueError, PermissionError) as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(ReviewDetailSerializer(review).data)

    @extend_schema(request=None, responses=ReviewDetailSerializer)
    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """Lock and submit a completed review draft."""
        review = get_object_or_404(Review, pk=pk, reviewer=request.user)
        try:
            review = ReviewService.submit_review(request.user, review.assignment)
        except (ValueError, PermissionError) as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ReviewDetailSerializer(review).data)

    @extend_schema(request=ReviewOverrideSerializer, responses=ReviewDetailSerializer)
    @action(detail=True, methods=['post'])
    def override(self, request, pk=None):
        """Organiser override of a locked review."""
        if not (request.user.is_organiser or request.user.is_admin):
            return Response(
                {'detail': 'Only organisers can override reviews.'},
                status=status.HTTP_403_FORBIDDEN
            )
        review = get_object_or_404(Review, pk=pk)
        serializer = ReviewOverrideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        reason = serializer.validated_data.pop('reason')
        try:
            review = ReviewService.override_review(request.user, review, serializer.validated_data, reason)
        except (ValueError, PermissionError) as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ReviewDetailSerializer(review).data)

    @extend_schema(
        parameters=[OpenApiParameter('submission', OpenApiTypes.UUID, description='Filter by submission ID')],
        responses=ReviewListSerializer(many=True),
    )
    @action(detail=False, methods=['get'], url_path='my-feedback')
    def my_feedback(self, request):
        """
        Author retrieves released reviewer feedback for their own submissions.
        Only returns reviews where the organiser has published the decision
        and explicitly released feedback to authors.
        Comments intended only for organisers are excluded.
        """
        qs = Review.objects.filter(
            submission__submitted_by=request.user,
            is_submitted=True,
            submission__decision__is_published=True,
            submission__decision__feedback_released=True,
        ).select_related(
            'submission__conference', 'reviewer', 'rubric', 'assignment'
        ).prefetch_related('scores')

        submission_id = request.query_params.get('submission')
        if submission_id:
            qs = qs.filter(submission=submission_id)

        page = self.paginate_queryset(qs)
        if page is not None:
            data = ReviewDetailSerializer(page, many=True).data
        else:
            data = ReviewDetailSerializer(qs, many=True).data

        for review in data:
            review.pop('comments_to_organisers', None)

        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)

    @extend_schema(
        parameters=[OpenApiParameter('submission', OpenApiTypes.UUID, required=True, description='Submission ID')],
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=['get'])
    def aggregate(self, request):
        """
        Get aggregate score breakdown for a submission.
        Organiser only.
        """
        if not (request.user.is_organiser or request.user.is_admin):
            return Response({'detail': 'Organisers only.'}, status=status.HTTP_403_FORBIDDEN)

        submission_id = request.query_params.get('submission')
        if not submission_id:
            return Response({'detail': 'submission query param required.'}, status=status.HTTP_400_BAD_REQUEST)

        if request.user.is_admin or request.user.is_superuser:
            submission = get_object_or_404(Submission, pk=submission_id)
        else:
            submission = get_object_or_404(
                Submission, pk=submission_id, conference__organiser=request.user
            )
        data = ReviewService.calculate_aggregate_score(submission)
        return Response(data)


class ReviewDecisionViewSet(viewsets.GenericViewSet):
    """
    Organiser decision management.

    list        GET  /decisions/?conference={id}
    retrieve    GET  /decisions/{id}/
    create      POST /decisions/
    publish     POST /decisions/{id}/publish/
    """
    queryset = ReviewDecision.objects.all()
    serializer_class = ReviewDecisionSerializer
    permission_classes = [IsAuthenticated]

    def _require_organiser(self):
        if not (self.request.user.is_organiser or self.request.user.is_admin):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only organisers can manage decisions.")

    def get_queryset(self):
        self._require_organiser()
        qs = ReviewDecision.objects.select_related(
            'submission', 'conference', 'decided_by'
        )
        if not (self.request.user.is_admin or self.request.user.is_superuser):
            qs = qs.filter(conference__organiser=self.request.user)

        conference = self.request.query_params.get('conference')
        if conference:
            qs = qs.filter(conference=conference)

        decision = self.request.query_params.get('decision')
        if decision:
            qs = qs.filter(decision=decision)

        published = self.request.query_params.get('is_published')
        if published is not None:
            qs = qs.filter(is_published=published.lower() == 'true')

        return qs

    @extend_schema(
        parameters=[
            OpenApiParameter('conference', OpenApiTypes.UUID, description='Filter by conference ID'),
            OpenApiParameter('decision', OpenApiTypes.STR, description='Filter by decision value'),
            OpenApiParameter('is_published', OpenApiTypes.BOOL, description='Filter by published status'),
        ],
        responses=ReviewDecisionSerializer(many=True),
    )
    def list(self, request):
        qs = self.get_queryset()
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(ReviewDecisionSerializer(page, many=True).data)
        return Response(ReviewDecisionSerializer(qs, many=True).data)

    @extend_schema(responses=ReviewDecisionSerializer)
    def retrieve(self, request, pk=None):
        decision = get_object_or_404(self.get_queryset(), pk=pk)
        return Response(ReviewDecisionSerializer(decision).data)

    @extend_schema(request=ReviewDecisionCreateSerializer, responses={201: ReviewDecisionSerializer})
    def create(self, request):
        self._require_organiser()
        serializer = ReviewDecisionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        submission = get_object_or_404(
            Submission, pk=serializer.validated_data['submission'],
            conference__organiser=request.user
        )
        try:
            decision = ReviewService.make_decision(
                organiser=request.user,
                submission=submission,
                decision=serializer.validated_data['decision'],
                reason=serializer.validated_data['decision_reason'],
                is_override=serializer.validated_data.get('is_override', False),
                override_reason=serializer.validated_data.get('override_reason', ''),
            )
        except (ValueError, PermissionError) as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(ReviewDecisionSerializer(decision).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=PublishDecisionSerializer, responses=ReviewDecisionSerializer)
    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        """Publish a decision — notifies the author and updates submission status."""
        self._require_organiser()
        decision = get_object_or_404(self.get_queryset(), pk=pk)
        serializer = PublishDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            decision = ReviewService.publish_decision(
                organiser=request.user,
                review_decision=decision,
                release_feedback=serializer.validated_data.get('release_feedback', False),
            )
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(ReviewDecisionSerializer(decision).data)
