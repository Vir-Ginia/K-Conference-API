"""
Notification Service
Handles in-app and email notifications for conference events.
"""

from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.conf import settings
from apps.communications.models import Notification
from apps.accounts.models import User
from apps.core.utils import send_email_template
import logging

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Service for managing notifications across the platform.
    """

    @staticmethod
    def create_notification(
        recipient,
        notification_type,
        title,
        message,
        priority='medium',
        related_object=None,
        expires_in_days=None,
        send_email=True
    ):
        """
        Create an in-app notification.

        Args:
            recipient: User instance
            notification_type: Type of notification
            title: Notification title
            message: Notification message
            priority: Priority level (low, medium, high, urgent)
            related_object: Object this notification relates to
            expires_in_days: Days until notification expires
            send_email: Whether to also send email notification
        """
        try:
            # Create notification
            notification = Notification.objects.create(
                recipient=recipient,
                notification_type=notification_type,
                title=title,
                message=message,
                priority=priority,
                expires_at=timezone.now() + timezone.timedelta(days=expires_in_days) if expires_in_days else None
            )

            # Set related object if provided
            if related_object:
                notification.content_type = ContentType.objects.get_for_model(related_object)
                notification.object_id = str(related_object.pk)
                notification.save()

            # Send email if requested and user prefers email notifications
            if send_email and getattr(getattr(recipient, 'profile', None), 'prefer_email_notifications', True):
                NotificationService._send_email_notification(notification)

            NotificationService._invalidate_unread_cache(recipient)
            logger.info(f"Created notification for {recipient.email}: {title}")
            return notification

        except Exception as e:
            logger.error(f"Failed to create notification: {e}")
            return None

    @staticmethod
    def bulk_create_notifications(
        recipients,
        notification_type,
        title,
        message,
        priority='medium',
        related_object=None,
        expires_in_days=None,
        send_email=True
    ):
        """
        Create notifications for multiple recipients.
        """
        notifications = []
        for recipient in recipients:
            notification = NotificationService.create_notification(
                recipient=recipient,
                notification_type=notification_type,
                title=title,
                message=message,
                priority=priority,
                related_object=related_object,
                expires_in_days=expires_in_days,
                send_email=send_email
            )
            if notification:
                notifications.append(notification)

        return notifications

    @staticmethod
    def _send_email_notification(notification):
        """
        Send email version of notification.
        """
        try:
            context = {
                'recipient': notification.recipient,
                'title': notification.title,
                'message': notification.message,
                'notification_type': notification.get_notification_type_display(),
                'created_at': notification.created_at,
            }

            send_email_template(
                subject=f"K-Conference: {notification.title}",
                template_name='emails/notification_email.html',
                context=context,
                recipient_list=[notification.recipient.email]
            )

            notification.is_email_sent = True
            notification.email_sent_at = timezone.now()
            notification.save(update_fields=['is_email_sent', 'email_sent_at'])

        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")

    @staticmethod
    def mark_notifications_read(user, notification_ids=None):
        """
        Mark notifications as read for a user.
        """
        queryset = Notification.objects.filter(recipient=user, is_read=False)

        if notification_ids:
            queryset = queryset.filter(id__in=notification_ids)

        count = queryset.update(is_read=True, read_at=timezone.now())
        NotificationService._invalidate_unread_cache(user)
        return count

    @staticmethod
    def _unread_cache_key(user):
        return f'notifications:unread_count:{user.pk}'

    @staticmethod
    def _invalidate_unread_cache(user):
        cache.delete(NotificationService._unread_cache_key(user))

    @staticmethod
    def get_unread_count(user):
        """
        Get count of unread notifications for a user.
        Cached for a short period — invalidated on create and mark-read.
        """
        cache_key = NotificationService._unread_cache_key(user)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        count = (
            Notification.objects.filter(recipient=user, is_read=False, expires_at__isnull=True).count()
            + Notification.objects.filter(recipient=user, is_read=False, expires_at__gt=timezone.now()).count()
        )
        timeout = getattr(settings, 'CACHE_TIMEOUT_UNREAD_COUNT', 120)
        cache.set(cache_key, count, timeout)
        return count

    @staticmethod
    def cleanup_expired_notifications():
        """
        Remove expired notifications.
        """
        expired_count = Notification.objects.filter(
            expires_at__lte=timezone.now()
        ).delete()[0]

        logger.info(f"Cleaned up {expired_count} expired notifications")
        return expired_count


# Global notification service instance
notification_service = NotificationService()