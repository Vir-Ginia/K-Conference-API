"""
Review service layer.
All review business logic lives here — not in views or serializers.
"""
import logging
from decimal import Decimal
from django.utils import timezone
from django.db import transaction

from apps.reviews.models import (
    ReviewAssignment, ConflictOfInterest, Review, ReviewScore, ReviewDecision
)
from apps.audit.models import AuditLogManager

logger = logging.getLogger(__name__)


class ReviewService:

    # ── Assignment ────────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def assign_reviewer(organiser, submission, reviewer, due_date=None):
        """
        Assign a reviewer to a submission.
        Enforces:
        - Reviewer cannot be an author of the submission.
        - No active conflict of interest exists.
        - No duplicate active assignment.
        - Conference is in review or open phase.
        """
        # Submission must be formally submitted before it can be reviewed
        if submission.status not in ('submitted', 'under_review'):
            raise ValueError(
                f"Cannot assign a reviewer: submission status is '{submission.status}'. "
                "Only submitted or under-review papers can be assigned."
            )

        # Conference must be in a review-appropriate phase
        conference = submission.conference
        if conference.status not in ('open', 'review'):
            raise ValueError(
                f"Cannot assign a reviewer: conference '{conference.short_name}' "
                f"is in '{conference.status}' status. Must be open or review."
            )

        # Reviewer must not be an author of this submission
        from django.db.models import Q
        is_author = submission.authors.filter(
            Q(user=reviewer) | Q(email=reviewer.email)
        ).exists()
        if is_author:
            raise ValueError("Reviewers cannot review their own submissions.")

        # Check for existing conflict of interest
        if ConflictOfInterest.objects.filter(
            reviewer=reviewer, submission=submission
        ).exists():
            raise ValueError(
                f"{reviewer.email} has declared a conflict of interest for this submission."
            )

        # Check for duplicate active assignment
        existing = ReviewAssignment.objects.filter(
            submission=submission, reviewer=reviewer
        ).first()
        if existing:
            if existing.is_active:
                raise ValueError(
                    f"{reviewer.email} is already assigned to this submission."
                )
            # Reactivate if previously deactivated
            existing.is_active = True
            existing.status = 'pending'
            existing.assigned_by = organiser
            existing.due_date = due_date
            existing.save()
            assignment = existing
        else:
            assignment = ReviewAssignment.objects.create(
                submission=submission,
                reviewer=reviewer,
                assigned_by=organiser,
                due_date=due_date,
            )

        AuditLogManager.log(
            action='review.assigned',
            actor=organiser,
            obj=assignment,
            new_values={
                'reviewer': reviewer.email,
                'submission': str(submission.id),
                'due_date': str(due_date) if due_date else None,
            }
        )

        ReviewService._notify_reviewer_assigned(assignment)
        return assignment

    @staticmethod
    def _notify_reviewer_assigned(assignment):
        """Send in-app notification + email to reviewer for a review assignment."""
        reviewer = assignment.reviewer
        submission = assignment.submission
        due_date = assignment.due_date

        # In-app notification
        try:
            from apps.communications.notification_service import notification_service
            due_str = due_date.strftime('%d %b %Y') if due_date else 'No deadline set'
            notification_service.create_notification(
                recipient=reviewer,
                notification_type='review_assigned',
                title=f'New Review Assignment: {submission.title[:60]}',
                message=(
                    f'You have been assigned to review "{submission.title}" '
                    f'for {submission.conference.title}. Due: {due_str}.'
                ),
                priority='high',
                related_object=assignment,
                send_email=False,  # sending dedicated email below
            )
        except Exception:
            logger.warning('Failed to create in-app notification for assignment %s', assignment.id)

        # Dedicated email
        try:
            from apps.core.utils import send_email_template
            send_email_template(
                subject=f'Review Assignment: {submission.title}',
                template_name='emails/review_assignment.html',
                context={
                    'recipient': reviewer,
                    'conference_title': submission.conference.title,
                    'submission_title': submission.title,
                    'assignment_id': str(assignment.id),
                    'track_name': submission.track.name if submission.track else None,
                    'due_date': due_date.strftime('%d %b %Y') if due_date else None,
                },
                recipient_list=[reviewer.email],
            )
        except Exception:
            logger.warning('Failed to send review assignment email for assignment %s', assignment.id)

    @staticmethod
    @transaction.atomic
    def unassign_reviewer(organiser, assignment):
        """Deactivate a review assignment."""
        assignment.is_active = False
        assignment.save(update_fields=['is_active'])

        AuditLogManager.log(
            action='review.unassigned',
            actor=organiser,
            obj=assignment,
            new_values={'reviewer': assignment.reviewer.email},
        )

    @staticmethod
    @transaction.atomic
    def respond_to_assignment(reviewer, assignment, accept):
        """Reviewer accepts or declines an assignment."""
        if assignment.reviewer != reviewer:
            raise PermissionError("You are not assigned to this review.")
        if not assignment.is_active:
            raise ValueError("This assignment is no longer active.")
        if assignment.status not in ('pending',):
            raise ValueError(f"Cannot respond: assignment is already '{assignment.status}'.")

        assignment.status = 'accepted' if accept else 'declined'
        if not accept:
            assignment.is_active = False
        assignment.save(update_fields=['status', 'is_active'])

        # Auto-create ConferenceRole on accept (skip if already exists)
        if accept:
            from apps.conferences.models import ConferenceRole
            ConferenceRole.objects.get_or_create(
                conference=assignment.submission.conference,
                user=reviewer,
                role='reviewer',
                defaults={'assigned_by': reviewer, 'is_active': True},
            )

        AuditLogManager.log(
            action='review.assignment.accepted' if accept else 'review.assignment.declined',
            actor=reviewer,
            obj=assignment,
        )
        return assignment

    # ── Conflict of Interest ──────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def declare_conflict(reviewer, submission, reason):
        """
        Reviewer declares a COI for a submission.
        Any active assignment for this pair is automatically recused.
        """
        if not reason or not reason.strip():
            raise ValueError("A reason is required when declaring a conflict of interest.")

        coi, created = ConflictOfInterest.objects.get_or_create(
            reviewer=reviewer,
            submission=submission,
            defaults={'reason': reason},
        )
        if not created:
            raise ValueError("You have already declared a conflict of interest for this submission.")

        # Recuse any active assignment
        ReviewAssignment.objects.filter(
            reviewer=reviewer,
            submission=submission,
            is_active=True
        ).update(status='recused', is_active=False)

        AuditLogManager.log(
            action='review.conflict_declared',
            actor=reviewer,
            obj=coi,
            new_values={
                'submission': str(submission.id),
                'reason': reason,
            }
        )
        return coi

    # ── Review Submission ─────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def save_review_draft(reviewer, assignment, review_data, scores_data):
        """
        Create or update a review draft (not yet submitted/locked).
        """
        if assignment.reviewer != reviewer:
            raise PermissionError("You are not assigned to this review.")
        if not assignment.is_active or assignment.status not in ('pending', 'accepted'):
            raise ValueError("This assignment is not active or has already been completed.")

        conference = assignment.submission.conference
        if conference.status not in ('open', 'review'):
            raise ValueError(
                f"Reviews cannot be saved: conference '{conference.short_name}' "
                f"is in '{conference.status}' status."
            )

        # Check COI
        if ConflictOfInterest.objects.filter(
            reviewer=reviewer, submission=assignment.submission
        ).exists():
            raise PermissionError(
                "You have declared a conflict of interest for this submission."
            )

        review, _ = Review.objects.get_or_create(
            assignment=assignment,
            defaults={
                'submission': assignment.submission,
                'reviewer': reviewer,
                'rubric': review_data.get('rubric'),
            }
        )

        if review.is_locked:
            raise PermissionError(
                "This review is locked. Contact the organiser to make changes."
            )

        # Update review fields
        for attr in ('recommendation', 'comments_to_authors', 'comments_to_organisers'):
            if attr in review_data:
                setattr(review, attr, review_data[attr])
        review.save()

        # Upsert scores
        rubric = review.rubric or assignment.submission.conference.review_rubrics.filter(
            is_default=True, is_active=True
        ).first()

        for score_data in scores_data:
            ReviewScore.objects.update_or_create(
                review=review,
                criterion_name=score_data['criterion_name'],
                defaults={
                    'criterion_weight': score_data.get('criterion_weight', Decimal('1.0')),
                    'score': score_data['score'],
                    'comment': score_data.get('comment', ''),
                }
            )

        return review

    @staticmethod
    @transaction.atomic
    def submit_review(reviewer, assignment):
        """
        Lock and submit a completed review draft.
        Validates all rubric criteria are scored and a recommendation is given.
        """
        try:
            review = assignment.review
        except Review.DoesNotExist:
            raise ValueError("No review draft found. Please save a draft before submitting.")

        if review.is_locked:
            raise ValueError("This review has already been submitted.")

        conference = assignment.submission.conference
        if conference.status not in ('open', 'review'):
            raise ValueError(
                f"Reviews cannot be submitted: conference '{conference.short_name}' "
                f"is in '{conference.status}' status."
            )

        if not review.recommendation:
            raise ValueError("A recommendation is required before submitting.")

        if not review.comments_to_authors.strip():
            raise ValueError("Comments to authors are required before submitting.")

        # Validate rubric criteria are all scored
        rubric = review.rubric or assignment.submission.conference.review_rubrics.filter(
            is_default=True, is_active=True
        ).first()

        if rubric:
            criteria_names = {c['name'] for c in rubric.criteria}
            scored_names = set(review.scores.values_list('criterion_name', flat=True))
            missing = criteria_names - scored_names
            if missing:
                raise ValueError(
                    f"The following criteria must be scored before submitting: {', '.join(missing)}"
                )

        # Compute aggregate weighted score
        aggregate = ReviewService._compute_weighted_score(review)
        review.aggregate_score = aggregate
        review.is_submitted = True
        review.is_locked = True
        review.submitted_at = timezone.now()
        review.save(update_fields=[
            'aggregate_score', 'is_submitted', 'is_locked', 'submitted_at'
        ])

        # Mark assignment complete
        assignment.status = 'completed'
        assignment.save(update_fields=['status'])

        AuditLogManager.log(
            action='review.submitted',
            actor=reviewer,
            obj=review,
            new_values={
                'recommendation': review.recommendation,
                'aggregate_score': str(aggregate),
            }
        )

        return review

    # ── Organiser Decision ────────────────────────────────────────────────────

    @staticmethod
    def calculate_aggregate_score(submission):
        """
        Compute the aggregate weighted score across all submitted reviews.
        Returns a dict with overall average and per-reviewer breakdown.
        """
        submitted_reviews = submission.reviews.filter(
            is_submitted=True
        ).prefetch_related('scores')

        if not submitted_reviews.exists():
            return {'aggregate': None, 'review_count': 0, 'breakdown': []}

        breakdown = []
        totals = []

        for review in submitted_reviews:
            score = ReviewService._compute_weighted_score(review)
            breakdown.append({
                'reviewer': review.reviewer.email,
                'score': float(score) if score else None,
                'recommendation': review.recommendation,
            })
            if score is not None:
                totals.append(float(score))

        aggregate = round(sum(totals) / len(totals), 2) if totals else None

        return {
            'aggregate': aggregate,
            'review_count': submitted_reviews.count(),
            'breakdown': breakdown,
        }

    @staticmethod
    @transaction.atomic
    def make_decision(organiser, submission, decision, reason, is_override=False, override_reason=''):
        """
        Record an organiser decision on a submission.
        If is_override=True, override_reason is mandatory and logged.
        """
        if not reason or not reason.strip():
            raise ValueError("A decision reason is required.")

        if is_override and not override_reason.strip():
            raise ValueError(
                "An override reason is required when overriding the score-based recommendation."
            )

        # Enforce minimum submitted reviews (unless organiser is overriding)
        submitted_count = submission.reviews.filter(is_submitted=True).count()
        if not is_override:
            min_reviews = 1
            if submission.track and submission.track.min_reviews_per_paper:
                min_reviews = submission.track.min_reviews_per_paper
            if submitted_count < min_reviews:
                raise ValueError(
                    f"At least {min_reviews} submitted review(s) are required before making a decision. "
                    f"Currently {submitted_count} submitted."
                )

        # Check for existing decision
        existing = ReviewDecision.objects.filter(submission=submission).first()
        if existing and existing.is_published:
            raise ValueError("Decision has already been published. It cannot be changed.")

        score_data = ReviewService.calculate_aggregate_score(submission)

        if existing:
            review_decision = existing
        else:
            review_decision = ReviewDecision(
                submission=submission,
                conference=submission.conference,
            )

        review_decision.decision = decision
        review_decision.decided_by = organiser
        review_decision.decision_reason = reason
        review_decision.aggregate_score = score_data['aggregate']
        review_decision.review_count = score_data['review_count']
        review_decision.is_override = is_override
        review_decision.override_reason = override_reason if is_override else ''
        review_decision.save()

        action = 'review.decision.override' if is_override else 'review.decision.made'
        AuditLogManager.log(
            action=action,
            actor=organiser,
            obj=review_decision,
            new_values={
                'decision': decision,
                'aggregate_score': str(score_data['aggregate']),
                'is_override': is_override,
            },
            reason=override_reason if is_override else reason,
        )

        return review_decision

    @staticmethod
    @transaction.atomic
    def publish_decision(organiser, review_decision, release_feedback=False):
        """
        Publish a decision — updates submission status and notifies the author.
        Optionally releases reviewer comments to the author.
        """
        if review_decision.is_published:
            raise ValueError("This decision has already been published.")

        submission = review_decision.submission

        # Map decision → submission status
        status_map = {
            'accept': 'accepted',
            'best_paper': 'accepted',
            'reject': 'rejected',
            'revision_required': 'revision_requested',
        }
        new_status = status_map.get(review_decision.decision, 'rejected')

        # Update submission
        submission.status = new_status
        submission.decision_note = review_decision.decision_reason
        submission.decision_by = organiser
        submission.decision_at = timezone.now()
        submission.save(update_fields=['status', 'decision_note', 'decision_by', 'decision_at'])

        review_decision.is_published = True
        review_decision.published_at = timezone.now()
        review_decision.feedback_released = release_feedback
        review_decision.save(update_fields=['is_published', 'published_at', 'feedback_released'])

        AuditLogManager.log(
            action='review.decision.published',
            actor=organiser,
            obj=review_decision,
            new_values={
                'decision': review_decision.decision,
                'submission': str(submission.id),
                'feedback_released': release_feedback,
            }
        )

        # Send dedicated decision notification email
        try:
            from apps.core.utils import send_email_template
            reviewer_feedback = None
            if release_feedback:
                comments = []
                for ra in submission.review_assignments.filter(status='completed'):
                    try:
                        has_review = ra.review is not None and ra.review.is_submitted
                    except Review.DoesNotExist:
                        has_review = False
                    if has_review:
                        if ra.review.comments_to_authors:
                            comments.append(ra.review.comments_to_authors)
                reviewer_feedback = '\n\n---\n\n'.join(comments) if comments else None

            send_email_template(
                subject=f'Decision on Your Submission: {submission.title}',
                template_name='emails/decision_notification.html',
                context={
                    'recipient': submission.submitted_by,
                    'conference_title': submission.conference.title,
                    'submission_title': submission.title,
                    'decision': review_decision.decision,
                    'decision_note': review_decision.decision_reason,
                    'feedback_released': release_feedback,
                    'reviewer_feedback': reviewer_feedback,
                },
                recipient_list=[submission.submitted_by.email],
            )
        except Exception:
            logger.warning('Failed to send decision notification email for submission %s', submission.id)

        return review_decision

    @staticmethod
    @transaction.atomic
    def override_review(organiser, review, updates, reason):
        """
        Organiser override of a locked review.
        Logs the override with mandatory reason.
        """
        if not reason or not reason.strip():
            raise ValueError("A reason is required for a review override.")

        for attr, value in updates.items():
            setattr(review, attr, value)

        review.override_by = organiser
        review.override_reason = reason
        review.override_at = timezone.now()
        review.save()

        AuditLogManager.log(
            action='review.override',
            actor=organiser,
            obj=review,
            new_values=updates,
            reason=reason,
        )
        return review

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _compute_weighted_score(review):
        """
        Compute the weighted average score for a single review.
        Formula: sum(score_i * weight_i) / sum(weight_i)
        """
        scores = list(review.scores.all())
        if not scores:
            return None

        total_weighted = sum(float(s.score) * float(s.criterion_weight) for s in scores)
        total_weight = sum(float(s.criterion_weight) for s in scores)

        if total_weight == 0:
            return None

        return Decimal(str(round(total_weighted / total_weight, 2)))


