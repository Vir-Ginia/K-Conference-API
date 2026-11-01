"""
Signals for the Submissions app.
Triggers notifications and audit logs on submission lifecycle events.
"""
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from apps.submissions.models import Submission, SubmissionFile
from apps.audit.models import AuditLogManager
from apps.communications.notification_service import notification_service


@receiver(pre_delete, sender=SubmissionFile)
def delete_submission_file_from_cloudinary(sender, instance, **kwargs):
    """Delete the Cloudinary asset whenever a SubmissionFile record is removed."""
    if instance.public_id:
        from apps.core.utils import delete_file_from_cloudinary
        delete_file_from_cloudinary(instance.public_id)


@receiver(post_save, sender=Submission)
def handle_submission_status_change(sender, instance, created, **kwargs):
    """
    On status transitions:
    - submitted       → notify the conference organiser
    - accepted        → notify the submitting author
    - rejected        → notify the submitting author
    - revision_requested → notify the submitting author
    """
    if created:
        return  # creation is handled by the service layer

    current_user = getattr(instance, '_current_user', None)
    status = instance.status

    if status == 'submitted':
        notification_service.create_notification(
            recipient=instance.conference.organiser,
            notification_type='submission_received',
            title=f'New Submission: {instance.title}',
            message=(
                f'A new paper "{instance.title}" has been submitted to '
                f'"{instance.conference.title}" by {instance.submitted_by.email}.'
            ),
            priority='medium',
            related_object=instance,
            send_email=True,
        )

    elif status == 'accepted':
        notification_service.create_notification(
            recipient=instance.submitted_by,
            notification_type='review_completed',
            title='Your Paper Has Been Accepted',
            message=(
                f'Congratulations! Your paper "{instance.title}" has been accepted '
                f'to "{instance.conference.title}".'
                + (f'\n\nNote: {instance.decision_note}' if instance.decision_note else '')
            ),
            priority='high',
            related_object=instance,
            send_email=True,
        )

    elif status == 'rejected':
        notification_service.create_notification(
            recipient=instance.submitted_by,
            notification_type='review_completed',
            title='Decision on Your Submission',
            message=(
                f'Your paper "{instance.title}" was not accepted to '
                f'"{instance.conference.title}".'
                + (f'\n\nFeedback: {instance.decision_note}' if instance.decision_note else '')
            ),
            priority='high',
            related_object=instance,
            send_email=True,
        )

    elif status == 'revision_requested':
        notification_service.create_notification(
            recipient=instance.submitted_by,
            notification_type='review_completed',
            title='Revision Requested for Your Submission',
            message=(
                f'A revision has been requested for your paper "{instance.title}" '
                f'submitted to "{instance.conference.title}".'
                + (f'\n\nDetails: {instance.decision_note}' if instance.decision_note else '')
            ),
            priority='high',
            related_object=instance,
            send_email=True,
        )

    AuditLogManager.log(
        action=f'submission.status.{status}',
        actor=current_user,
        obj=instance,
        new_values={'status': status},
    )
