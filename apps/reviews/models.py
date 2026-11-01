"""
Review management models.
Covers the full peer-review lifecycle: assignment, COI declaration,
rubric-based scoring, and organiser decision-making.
"""
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from apps.accounts.models import User
import uuid


class ReviewAssignment(models.Model):
    """
    Links a reviewer to a submission.
    Organisers create assignments; reviewers accept, decline, or recuse.
    """

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('completed', 'Completed'),
        ('recused', 'Recused (COI)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission = models.ForeignKey(
        'submissions.Submission',
        on_delete=models.CASCADE,
        related_name='review_assignments'
    )
    reviewer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='review_assignments'
    )
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_review_assignments'
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    is_active = models.BooleanField(default=True)

    due_date = models.DateTimeField(null=True, blank=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'review_assignments'
        unique_together = [('submission', 'reviewer')]
        ordering = ['-assigned_at']
        indexes = [
            models.Index(fields=['reviewer', 'status', 'is_active']),
            models.Index(fields=['submission', 'status']),
        ]

    def __str__(self):
        return f"{self.reviewer.email} → {self.submission.title[:50]}"


class ConflictOfInterest(models.Model):
    """
    Reviewer declares a conflict of interest for a submission.
    Automatically recuses the reviewer from that assignment.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reviewer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='conflicts_of_interest'
    )
    submission = models.ForeignKey(
        'submissions.Submission',
        on_delete=models.CASCADE,
        related_name='conflicts_of_interest'
    )
    reason = models.TextField(help_text="Explanation of the conflict")

    # Organiser can review/acknowledge the COI
    acknowledged_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='acknowledged_cois'
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    declared_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'conflicts_of_interest'
        unique_together = [('reviewer', 'submission')]
        ordering = ['-declared_at']

    def __str__(self):
        return f"COI: {self.reviewer.email} / {self.submission.title[:50]}"


class Review(models.Model):
    """
    The actual review submitted by a reviewer.
    Locked once submitted — organiser override required for any changes.
    """

    RECOMMENDATION_CHOICES = [
        ('strong_accept', 'Strong Accept'),
        ('accept', 'Accept'),
        ('weak_accept', 'Weak Accept'),
        ('borderline', 'Borderline'),
        ('weak_reject', 'Weak Reject'),
        ('reject', 'Reject'),
        ('strong_reject', 'Strong Reject'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assignment = models.OneToOneField(
        ReviewAssignment,
        on_delete=models.CASCADE,
        related_name='review'
    )
    submission = models.ForeignKey(
        'submissions.Submission',
        on_delete=models.CASCADE,
        related_name='reviews'
    )
    reviewer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='reviews'
    )
    rubric = models.ForeignKey(
        'conferences.ReviewRubric',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reviews'
    )

    # Feedback
    recommendation = models.CharField(
        max_length=20, choices=RECOMMENDATION_CHOICES, null=True, blank=True
    )
    comments_to_authors = models.TextField(
        blank=True,
        help_text="Feedback visible to the paper authors (after decision)"
    )
    comments_to_organisers = models.TextField(
        blank=True,
        help_text="Confidential notes visible only to organisers"
    )

    # Computed aggregate score (set on submission)
    aggregate_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Weighted aggregate score computed from rubric criteria"
    )

    # Status
    is_submitted = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(null=True, blank=True)
    is_locked = models.BooleanField(
        default=False,
        help_text="Locked after submission — organiser override required"
    )

    # Organiser override tracking
    override_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='review_overrides'
    )
    override_reason = models.TextField(blank=True)
    override_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reviews'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['submission', 'is_submitted']),
            models.Index(fields=['reviewer', 'is_submitted']),
        ]

    def __str__(self):
        return f"Review by {self.reviewer.email} — {self.submission.title[:50]}"

    @property
    def is_positive_recommendation(self):
        return self.recommendation in ('strong_accept', 'accept', 'weak_accept')


class ReviewScore(models.Model):
    """
    Per-criterion score within a review.
    Criterion name and weight are snapshotted from the rubric at review time.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    review = models.ForeignKey(
        Review,
        on_delete=models.CASCADE,
        related_name='scores'
    )
    criterion_name = models.CharField(max_length=255)
    criterion_weight = models.DecimalField(
        max_digits=6, decimal_places=2,
        help_text="Weight snapshot from rubric at time of review"
    )
    score = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    comment = models.TextField(blank=True, help_text="Optional per-criterion comment")

    class Meta:
        db_table = 'review_scores'
        unique_together = [('review', 'criterion_name')]

    def __str__(self):
        return f"{self.criterion_name}: {self.score} (×{self.criterion_weight})"

    @property
    def weighted_score(self):
        return float(self.score) * float(self.criterion_weight)


class ReviewDecision(models.Model):
    """
    Organiser's final accept/reject decision on a submission.
    Informed by aggregate review scores; overrides are logged.
    """

    DECISION_CHOICES = [
        ('accept', 'Accept'),
        ('reject', 'Reject'),
        ('revision_required', 'Revision Required'),
        ('best_paper', 'Best Paper'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission = models.OneToOneField(
        'submissions.Submission',
        on_delete=models.CASCADE,
        related_name='decision'
    )
    conference = models.ForeignKey(
        'conferences.Conference',
        on_delete=models.CASCADE,
        related_name='decisions'
    )
    decision = models.CharField(max_length=20, choices=DECISION_CHOICES)
    decided_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='review_decisions'
    )

    # Score context at decision time
    aggregate_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Aggregate score computed at decision time"
    )
    review_count = models.PositiveIntegerField(
        default=0, help_text="Number of submitted reviews considered"
    )

    decision_reason = models.TextField(help_text="Organiser rationale for the decision")

    # Override tracking (for tie-breaks / exceptional cases)
    is_override = models.BooleanField(
        default=False,
        help_text="True if this overrides the score-based recommendation"
    )
    override_reason = models.TextField(
        blank=True,
        help_text="Required when is_override=True"
    )

    # Publishing
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    feedback_released = models.BooleanField(
        default=False,
        help_text="Whether reviewer comments have been released to the author"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'review_decisions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['conference', 'decision', 'is_published']),
            models.Index(fields=['submission', 'is_published']),
        ]

    def __str__(self):
        return f"{self.get_decision_display()} — {self.submission.title[:50]}"
