"""
Submission management models.
Handles the full lifecycle of conference paper submissions.
"""
from django.db import models
from django.utils import timezone
from apps.accounts.models import User
import uuid


class Submission(models.Model):

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('under_review', 'Under Review'),
        ('revision_requested', 'Revision Requested'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('withdrawn', 'Withdrawn'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conference = models.ForeignKey(
        'conferences.Conference',
        on_delete=models.CASCADE,
        related_name='submissions'
    )
    track = models.ForeignKey(
        'conferences.ConferenceTrack',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='submissions'
    )
    submitted_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='submissions'
    )

    # Paper content
    title = models.CharField(max_length=500)
    abstract = models.TextField()
    keywords = models.JSONField(default=list, help_text="List of keyword strings")

    # Status & versioning
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    version_number = models.PositiveIntegerField(default=1)
    is_locked = models.BooleanField(
        default=False,
        help_text="Locked after submission deadline — only organiser can override"
    )

    # Organiser deadline override tracking
    deadline_override = models.BooleanField(default=False)
    deadline_override_reason = models.TextField(blank=True)
    deadline_override_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='submission_overrides'
    )
    deadline_override_at = models.DateTimeField(null=True, blank=True)

    # Decision fields
    decision_note = models.TextField(blank=True, help_text="Organiser note on final decision")
    decision_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='submission_decisions'
    )
    decision_at = models.DateTimeField(null=True, blank=True)

    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'submissions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['conference', 'status']),
            models.Index(fields=['submitted_by', 'status']),
            models.Index(fields=['track', 'status']),
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f"{self.title} ({self.conference.short_name})"

    @property
    def is_editable(self):
        """Author can edit only if not locked and not in a terminal state."""
        if self.is_locked:
            return False
        return self.status not in ('accepted', 'rejected', 'withdrawn')

    @property
    def is_terminal(self):
        return self.status in ('accepted', 'rejected', 'withdrawn')

    def lock(self):
        self.is_locked = True
        self.save(update_fields=['is_locked'])


class SubmissionAuthor(models.Model):
    """Authors of a submission — primary + co-authors, including non-registered users."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission = models.ForeignKey(
        Submission,
        on_delete=models.CASCADE,
        related_name='authors'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='co_authored_submissions'
    )

    # Denormalised — supports external/non-registered co-authors
    name = models.CharField(max_length=255)
    email = models.EmailField()
    affiliation = models.CharField(max_length=500, blank=True)

    order = models.PositiveSmallIntegerField(
        default=0,
        help_text="Display order; 0 = primary author"
    )
    is_primary = models.BooleanField(default=False)
    is_corresponding = models.BooleanField(default=False)

    class Meta:
        db_table = 'submission_authors'
        ordering = ['order']
        unique_together = [('submission', 'email')]

    def __str__(self):
        return f"{self.name} — {self.submission.title}"


class SubmissionFile(models.Model):
    """Files attached to a submission. Supports versioning."""

    FILE_TYPE_CHOICES = [
        ('paper', 'Full Paper'),
        ('abstract', 'Abstract'),
        ('supplementary', 'Supplementary Material'),
        ('presentation', 'Presentation'),
    ]

    MEDIA_CATEGORY_CHOICES = [
        ('document', 'Document'),
        ('image', 'Image'),
        ('audio', 'Audio'),
        ('video', 'Video'),
        ('other', 'Other'),
    ]

    DOCUMENT_MIME_TYPES = {
        'application/pdf', 'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-powerpoint',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        'text/plain', 'application/rtf',
    }
    IMAGE_MIME_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml'}
    AUDIO_MIME_TYPES = {'audio/mpeg', 'audio/wav', 'audio/ogg', 'audio/mp4', 'audio/aac'}
    VIDEO_MIME_TYPES = {'video/mp4', 'video/mpeg', 'video/ogg', 'video/webm', 'video/quicktime'}

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission = models.ForeignKey(
        Submission,
        on_delete=models.CASCADE,
        related_name='files'
    )
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='uploaded_submission_files'
    )

    file_type = models.CharField(max_length=20, choices=FILE_TYPE_CHOICES, default='paper')
    file_url = models.URLField()
    public_id = models.CharField(max_length=500, blank=True)
    original_filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(help_text="Size in bytes")
    mime_type = models.CharField(max_length=100, blank=True)

    version_number = models.PositiveIntegerField(default=1)
    is_current = models.BooleanField(default=True)

    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'submission_files'
        ordering = ['-version_number', '-uploaded_at']
        indexes = [
            models.Index(fields=['submission', 'is_current']),
            models.Index(fields=['submission', 'file_type', 'is_current']),
        ]

    def __str__(self):
        return f"{self.original_filename} (v{self.version_number})"

    @property
    def media_category(self):
        """Detect whether the file is a document, image, audio, video, or other."""
        mime = (self.mime_type or '').lower()
        if mime in self.DOCUMENT_MIME_TYPES or mime.startswith('text/'):
            return 'document'
        if mime in self.IMAGE_MIME_TYPES or mime.startswith('image/'):
            return 'image'
        if mime in self.AUDIO_MIME_TYPES or mime.startswith('audio/'):
            return 'audio'
        if mime in self.VIDEO_MIME_TYPES or mime.startswith('video/'):
            return 'video'
        return 'other'

    @property
    def is_document(self):
        return self.media_category == 'document'

    @property
    def is_image(self):
        return self.media_category == 'image'

    @property
    def is_audio(self):
        return self.media_category == 'audio'

    @property
    def is_video(self):
        return self.media_category == 'video'


class SubmissionVersion(models.Model):
    """Snapshot of a submission at a specific version. Created on organiser override."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission = models.ForeignKey(
        Submission,
        on_delete=models.CASCADE,
        related_name='versions'
    )
    version_number = models.PositiveIntegerField()

    # Content snapshot
    title = models.CharField(max_length=500)
    abstract = models.TextField()
    keywords = models.JSONField(default=list)

    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='submission_version_changes'
    )
    change_reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'submission_versions'
        ordering = ['-version_number']
        unique_together = [('submission', 'version_number')]

    def __str__(self):
        return f"{self.submission.title} — v{self.version_number}"
