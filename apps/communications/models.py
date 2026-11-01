"""Models for Communications"""
from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from apps.accounts.models import User
import uuid


class Announcement(models.Model):
    """Conference announcements and news"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    content = models.TextField()
    conference = models.ForeignKey(
        'conferences.Conference',
        on_delete=models.CASCADE,
        related_name='announcements'
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='announcements'
    )
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'announcements'
        ordering = ['-published_at', '-created_at']
        indexes = [
            models.Index(fields=['conference', 'is_published']),
            models.Index(fields=['author']),
        ]

    def __str__(self):
        return f"{self.conference.short_name}: {self.title}"


class Notification(models.Model):
    """In-app notifications for users"""

    NOTIFICATION_TYPES = [
        ('conference_created', 'Conference Created'),
        ('conference_updated', 'Conference Updated'),
        ('conference_opened', 'Conference Opened'),
        ('conference_closed', 'Conference Closed'),
        ('deadline_approaching', 'Deadline Approaching'),
        ('role_assigned', 'Role Assigned'),
        ('submission_received', 'Submission Received'),
        ('review_assigned', 'Review Assigned'),
        ('review_completed', 'Review Completed'),
        ('announcement', 'New Announcement'),
        ('system', 'System Message'),
    ]

    PRIORITY_LEVELS = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notifications'
    )

    # Notification content
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=255)
    message = models.TextField()
    priority = models.CharField(max_length=10, choices=PRIORITY_LEVELS, default='medium')

    # Related object (generic relation)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.CharField(max_length=255, blank=True, null=True)
    content_object = GenericForeignKey('content_type', 'object_id')

    # Status
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    is_email_sent = models.BooleanField(default=False)
    email_sent_at = models.DateTimeField(null=True, blank=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True, help_text="Auto-delete after this date")

    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read', 'created_at']),
            models.Index(fields=['notification_type', 'created_at']),
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['expires_at']),
        ]

    def __str__(self):
        return f"{self.recipient.email}: {self.title}"

    def mark_as_read(self):
        """Mark notification as read."""
        from django.utils import timezone
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])

    @property
    def is_expired(self):
        """Check if notification has expired."""
        if not self.expires_at:
            return False
        from django.utils import timezone
        return timezone.now() > self.expires_at


class FAQItem(models.Model):
    """
    FAQ / info area items for a conference.
    Organisers can create, update, reorder, and publish entries at any time —
    including during the event.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conference = models.ForeignKey(
        'conferences.Conference',
        on_delete=models.CASCADE,
        related_name='faq_items',
    )
    question = models.CharField(max_length=500)
    answer = models.TextField()
    category = models.CharField(max_length=100, blank=True, help_text="Optional grouping label")
    order = models.PositiveIntegerField(default=0, help_text="Display order within the conference FAQ")
    is_published = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='faq_items_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'faq_items'
        ordering = ['order', 'created_at']
        indexes = [
            models.Index(fields=['conference', 'is_published']),
        ]

    def __str__(self):
        return f"[{self.conference.short_name}] {self.question[:80]}"
