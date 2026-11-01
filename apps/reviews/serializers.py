"""Serializers for the Reviews app."""
from rest_framework import serializers
from django.utils import timezone
from apps.reviews.models import (
    ReviewAssignment, ConflictOfInterest, Review, ReviewScore, ReviewDecision
)


# ── Assignment ────────────────────────────────────────────────────────────────

class ReviewAssignmentListSerializer(serializers.ModelSerializer):
    reviewer_email = serializers.EmailField(source='reviewer.email', read_only=True)
    reviewer_name = serializers.SerializerMethodField()
    submission_title = serializers.CharField(source='submission.title', read_only=True)
    conference_name = serializers.CharField(source='submission.conference.title', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    has_review = serializers.SerializerMethodField()

    class Meta:
        model = ReviewAssignment
        fields = [
            'id', 'submission', 'submission_title', 'conference_name',
            'reviewer', 'reviewer_email', 'reviewer_name',
            'status', 'status_display', 'is_active',
            'due_date', 'has_review', 'assigned_at',
        ]

    def get_reviewer_name(self, obj):
        return obj.reviewer.get_full_name() or obj.reviewer.email

    def get_has_review(self, obj):
        try:
            return obj.review is not None
        except Review.DoesNotExist:
            return False


class ReviewAssignmentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewAssignment
        fields = ['submission', 'reviewer', 'due_date']

    def validate(self, attrs):
        submission = attrs['submission']
        reviewer = attrs['reviewer']

        # Enforce reviewer role
        if not reviewer.is_reviewer:
            raise serializers.ValidationError(
                {"reviewer": "This user does not have the Reviewer role."}
            )
        return attrs


# ── Conflict of Interest ──────────────────────────────────────────────────────

class ConflictOfInterestSerializer(serializers.ModelSerializer):
    reviewer_email = serializers.EmailField(source='reviewer.email', read_only=True)
    submission_title = serializers.CharField(source='submission.title', read_only=True)
    acknowledged_by_email = serializers.SerializerMethodField()

    class Meta:
        model = ConflictOfInterest
        fields = [
            'id', 'reviewer', 'reviewer_email', 'submission', 'submission_title',
            'reason', 'acknowledged_by_email', 'acknowledged_at', 'declared_at',
        ]
        read_only_fields = ['reviewer', 'acknowledged_by_email', 'acknowledged_at', 'declared_at']

    def get_acknowledged_by_email(self, obj):
        return obj.acknowledged_by.email if obj.acknowledged_by else None


class ConflictOfInterestCreateSerializer(serializers.Serializer):
    submission = serializers.UUIDField()
    reason = serializers.CharField()

    def validate_reason(self, value):
        if not value.strip():
            raise serializers.ValidationError("Reason cannot be blank.")
        return value


# ── Review Scores ─────────────────────────────────────────────────────────────

class ReviewScoreSerializer(serializers.ModelSerializer):
    weighted_score = serializers.FloatField(read_only=True)

    class Meta:
        model = ReviewScore
        fields = ['id', 'criterion_name', 'criterion_weight', 'score', 'comment', 'weighted_score']


class ReviewScoreInputSerializer(serializers.Serializer):
    criterion_name = serializers.CharField()
    criterion_weight = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, default=1)
    score = serializers.IntegerField(min_value=1, max_value=10)
    comment = serializers.CharField(required=False, allow_blank=True, default='')


# ── Review ────────────────────────────────────────────────────────────────────

class ReviewListSerializer(serializers.ModelSerializer):
    reviewer_email = serializers.EmailField(source='reviewer.email', read_only=True)
    submission_title = serializers.CharField(source='submission.title', read_only=True)
    recommendation_display = serializers.CharField(source='get_recommendation_display', read_only=True)
    score_count = serializers.IntegerField(source='scores.count', read_only=True)

    class Meta:
        model = Review
        fields = [
            'id', 'submission', 'submission_title', 'reviewer_email',
            'recommendation', 'recommendation_display',
            'aggregate_score', 'score_count',
            'is_submitted', 'is_locked', 'submitted_at', 'created_at',
        ]


class ReviewDetailSerializer(serializers.ModelSerializer):
    reviewer_email = serializers.EmailField(source='reviewer.email', read_only=True)
    submission_title = serializers.CharField(source='submission.title', read_only=True)
    recommendation_display = serializers.CharField(source='get_recommendation_display', read_only=True)
    scores = ReviewScoreSerializer(many=True, read_only=True)
    rubric_name = serializers.CharField(source='rubric.name', read_only=True, default=None)
    override_by_email = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            'id', 'submission', 'submission_title',
            'reviewer_email', 'rubric', 'rubric_name',
            'recommendation', 'recommendation_display',
            'comments_to_authors', 'comments_to_organisers',
            'aggregate_score', 'scores',
            'is_submitted', 'is_locked', 'submitted_at',
            'override_by_email', 'override_reason', 'override_at',
            'created_at', 'updated_at',
        ]

    def get_override_by_email(self, obj):
        return obj.override_by.email if obj.override_by else None


class ReviewDraftSerializer(serializers.Serializer):
    """Used when a reviewer saves or updates a draft review."""
    rubric = serializers.UUIDField(required=False, allow_null=True)
    recommendation = serializers.ChoiceField(
        choices=Review.RECOMMENDATION_CHOICES, required=False, allow_blank=True
    )
    comments_to_authors = serializers.CharField(required=False, allow_blank=True)
    comments_to_organisers = serializers.CharField(required=False, allow_blank=True)
    scores = ReviewScoreInputSerializer(many=True, required=False)


class ReviewOverrideSerializer(serializers.Serializer):
    recommendation = serializers.ChoiceField(choices=Review.RECOMMENDATION_CHOICES, required=False)
    comments_to_authors = serializers.CharField(required=False)
    comments_to_organisers = serializers.CharField(required=False)
    reason = serializers.CharField()

    def validate_reason(self, value):
        if not value.strip():
            raise serializers.ValidationError("Override reason cannot be blank.")
        return value


# ── Decision ──────────────────────────────────────────────────────────────────

class ReviewDecisionSerializer(serializers.ModelSerializer):
    decided_by_email = serializers.EmailField(source='decided_by.email', read_only=True)
    submission_title = serializers.CharField(source='submission.title', read_only=True)
    decision_display = serializers.CharField(source='get_decision_display', read_only=True)

    class Meta:
        model = ReviewDecision
        fields = [
            'id', 'submission', 'submission_title', 'conference',
            'decision', 'decision_display', 'decided_by_email',
            'aggregate_score', 'review_count',
            'decision_reason', 'is_override', 'override_reason',
            'is_published', 'published_at', 'feedback_released',
            'created_at', 'updated_at',
        ]


class ReviewDecisionCreateSerializer(serializers.Serializer):
    submission = serializers.UUIDField()
    decision = serializers.ChoiceField(choices=ReviewDecision.DECISION_CHOICES)
    decision_reason = serializers.CharField()
    is_override = serializers.BooleanField(default=False)
    override_reason = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, attrs):
        if attrs.get('is_override') and not attrs.get('override_reason', '').strip():
            raise serializers.ValidationError(
                {"override_reason": "Override reason is required when is_override is true."}
            )
        return attrs


class PublishDecisionSerializer(serializers.Serializer):
    release_feedback = serializers.BooleanField(
        default=False,
        help_text="Whether to release reviewer comments to the submitting author."
    )
