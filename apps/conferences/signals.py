"""
Django signals for Conferences app.
Automatic updates and notifications for conference-related events.
"""

from django.db.models.signals import post_save, pre_save, pre_delete
from django.dispatch import receiver
from django.utils import timezone
from apps.conferences.models import Conference, ConferenceTrack, ConferenceRole, ConferenceDeadline, ConferenceMedia
from apps.audit.models import AuditLogManager
from apps.communications.notification_service import notification_service


@receiver(post_save, sender=Conference)
def log_conference_changes(sender, instance, created, **kwargs):
    """
    Log conference creation and major updates with notifications.
    """
    current_user = getattr(instance, '_current_user', None)

    if created:
        action = 'conference.created'
        new_values = {
            'title': instance.title,
            'short_name': instance.short_name,
            'status': instance.status,
            'start_date': str(instance.start_date),
            'organiser': instance.organiser.email,
        }

        # Notify organiser — single combined email covering creation + organiser role
        notification_service.create_notification(
            recipient=instance.organiser,
            notification_type='conference_created',
            title=f'Conference "{instance.title}" Created',
            message=(
                f'Your conference "{instance.title}" has been successfully created and is ready for setup.\n\n'
                f'You have been assigned as the organiser. You can now add tracks, set deadlines, '
                f'upload branding, and configure the review rubric before opening submissions.'
            ),
            priority='medium',
            related_object=instance,
            send_email=True
        )

    else:
        action = 'conference.updated'
        new_values = {
            'status': instance.status,
            'title': instance.title,
        }

        # Notify about status changes
        if hasattr(instance, '_status_changed') and instance._status_changed:
            old_status = getattr(instance, '_old_status', 'draft')
            new_status = instance.status

            # Notify all conference participants about status changes
            from apps.accounts.models import User as UserModel
            participant_ids = instance.user_roles.filter(is_active=True).values_list('user', flat=True)
            participants = UserModel.objects.filter(id__in=participant_ids)
            if participants.exists():
                status_messages = {
                    'open': f'Conference "{instance.title}" is now open for submissions and registrations!',
                    'review': f'Conference "{instance.title}" has closed submissions and entered review phase.',
                    'closed': f'Conference "{instance.title}" has concluded. Results will be published soon.',
                    'archived': f'Conference "{instance.title}" has been archived.',
                }

                message = status_messages.get(new_status, f'Conference "{instance.title}" status changed to {new_status}.')

                notification_service.bulk_create_notifications(
                    recipients=participants,
                    notification_type=f'conference_{new_status}',
                    title=f'Conference Status Update: {instance.title}',
                    message=message,
                    priority='high' if new_status in ['open', 'closed'] else 'medium',
                    related_object=instance,
                    send_email=True
                )

    AuditLogManager.log(
        action=action,
        actor=current_user,
        obj=instance,
        new_values=new_values
    )


@receiver(post_save, sender=ConferenceTrack)
def log_track_changes(sender, instance, created, **kwargs):
    """
    Log track creation and updates with notifications.
    """
    current_user = getattr(instance, '_current_user', None)

    if created:
        action = 'conference.track.created'

        # Notify track chair only once conference is open
        if instance.chair and instance.conference.status == 'open':
            notification_service.create_notification(
                recipient=instance.chair,
                notification_type='role_assigned',
                title=f'Assigned as Track Chair: {instance.name}',
                message=f'You have been assigned as chair for the track "{instance.name}" in conference "{instance.conference.title}".',
                priority='medium',
                related_object=instance,
                send_email=True
            )
    else:
        action = 'conference.track.updated'

    AuditLogManager.log(
        action=action,
        actor=current_user,
        obj=instance,
        new_values={
            'conference': instance.conference.short_name,
            'name': instance.name,
            'chair': instance.chair.email if instance.chair else None,
        }
    )


@receiver(post_save, sender=ConferenceRole)
def log_role_assignments(sender, instance, created, **kwargs):
    """
    Log role assignments and changes with notifications.
    """
    if created:
        action = 'conference.role.assigned'

        # Notify user about role assignment
        role_messages = {
            'organiser': f'You have been assigned as organiser for conference "{instance.conference.title}".',
            'track_chair': f'You have been assigned as track chair for "{instance.track.name if instance.track else "General"}" in conference "{instance.conference.title}".',
            'reviewer': f'You have been assigned as a reviewer for conference "{instance.conference.title}".',
            'participant': f'You have been registered as a participant for conference "{instance.conference.title}".',
            'keynote_speaker': f'You have been assigned as a keynote speaker for conference "{instance.conference.title}".',
            'sponsor': f'You have been registered as a sponsor for conference "{instance.conference.title}".',
        }

        message = role_messages.get(instance.role, f'You have been assigned the role "{instance.role}" for conference "{instance.conference.title}".')

        # Organiser role email is already sent as part of the conference creation notification
        notification_service.create_notification(
            recipient=instance.user,
            notification_type='role_assigned',
            title=f'Role Assigned: {instance.get_role_display()}',
            message=message,
            priority='medium',
            related_object=instance,
            send_email=instance.role != 'organiser',
        )
    else:
        action = 'conference.role.updated'

    AuditLogManager.log(
        action=action,
        actor=instance.assigned_by,
        obj=instance,
        new_values={
            'conference': instance.conference.short_name,
            'user': instance.user.email,
            'role': instance.role,
            'track': instance.track.name if instance.track else None,
        }
    )


@receiver(post_save, sender=ConferenceDeadline)
def log_deadline_changes(sender, instance, created, **kwargs):
    """
    Log deadline creation and updates with notifications.
    """
    current_user = getattr(instance, '_current_user', None)

    if created:
        action = 'conference.deadline.created'

        # Notify all conference participants about new deadlines
        from apps.accounts.models import User as UserModel
        participant_ids = instance.conference.user_roles.filter(is_active=True).values_list('user', flat=True)
        participants = UserModel.objects.filter(id__in=participant_ids)
        if participants.exists():
            notification_service.bulk_create_notifications(
                recipients=participants,
                notification_type='system',
                title=f'New Deadline: {instance.title}',
                message=f'A new deadline has been set for conference "{instance.conference.title}": {instance.title} - {instance.deadline_date.strftime("%B %d, %Y")}.',
                priority='medium',
                related_object=instance,
                send_email=True,
                expires_in_days=30
            )
    else:
        action = 'conference.deadline.updated'

    AuditLogManager.log(
        action=action,
        actor=current_user,
        obj=instance,
        new_values={
            'conference': instance.conference.short_name,
            'deadline_type': instance.deadline_type,
            'title': instance.title,
            'deadline_date': str(instance.deadline_date),
        }
    )


@receiver(pre_save, sender=Conference)
def track_status_changes(sender, instance, **kwargs):
    """
    Track status changes for logging and notifications.
    """
    if instance.pk:
        try:
            old_instance = Conference.objects.get(pk=instance.pk)
            if old_instance.status != instance.status:
                instance._status_changed = True
                instance._old_status = old_instance.status
        except Conference.DoesNotExist:
            pass


@receiver(pre_delete, sender=ConferenceMedia)
def delete_conference_media_from_cloudinary(sender, instance, **kwargs):
    """Delete the Cloudinary asset whenever a ConferenceMedia record is removed."""
    if instance.public_id:
        from apps.core.utils import delete_file_from_cloudinary
        delete_file_from_cloudinary(instance.public_id)


@receiver(post_save, sender=ConferenceMedia)
def log_media_changes(sender, instance, created, **kwargs):
    """
    Log media uploads and changes.
    """
    current_user = getattr(instance, '_current_user', None)

    if created:
        action = 'conference.media.uploaded'

        # Notify conference organiser about new media
        if instance.uploaded_by != instance.conference.organiser:
            notification_service.create_notification(
                recipient=instance.conference.organiser,
                notification_type='system',
                title=f'New Media Uploaded: {instance.title}',
                message=f'New {instance.get_mediatype_display()} "{instance.title}" has been uploaded to conference "{instance.conference.title}".',
                priority='low',
                related_object=instance,
                send_email=False,
                expires_in_days=7
            )
    else:
        action = 'conference.media.updated'

    AuditLogManager.log(
        action=action,
        actor=current_user or instance.uploaded_by,
        obj=instance,
        new_values={
            'conference': instance.conference.short_name,
            'mediatype': instance.mediatype,
            'title': instance.title,
            'file_url': instance.file_url,
        }
    )