"""Signals for the Reviews app."""
from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.reviews.models import ReviewAssignment, Review
from apps.communications.notification_service import notification_service
from apps.audit.models import AuditLogManager


@receiver(post_save, sender=ReviewAssignment)
def notify_reviewer_on_assignment(sender, instance, created, **kwargs):
    """Notify reviewer when they are assigned to a submission."""
    if not created:
        return

    notification_service.create_notification(
        recipient=instance.reviewer,
        notification_type='review_assigned',
        title=f'Review Assignment: {instance.submission.title[:80]}',
        message=(
            f'You have been assigned to review "{instance.submission.title}" '
            f'for "{instance.submission.conference.title}".'
            + (f' Due: {instance.due_date.strftime("%B %d, %Y")}' if instance.due_date else '')
        ),
        priority='high',
        related_object=instance,
        send_email=True,
    )


@receiver(post_save, sender=Review)
def notify_on_review_submitted(sender, instance, created, **kwargs):
    """
    When a review is submitted, check if all active assignments for the submission
    are now complete. If so, notify the organiser that the submission is ready for a decision.
    """
    if not instance.is_submitted:
        return

    submission = instance.submission
    active_assignments = submission.review_assignments.filter(is_active=True)
    all_done = not active_assignments.exclude(status='completed').exists()

    if all_done and active_assignments.exists():
        notification_service.create_notification(
            recipient=submission.conference.organiser,
            notification_type='review_completed',
            title=f'All Reviews Complete: {submission.title[:80]}',
            message=(
                f'All reviews for "{submission.title}" in "{submission.conference.title}" '
                f'are now complete. The submission is ready for a decision.'
            ),
            priority='high',
            related_object=submission,
            send_email=True,
        )
