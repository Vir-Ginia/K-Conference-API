"""
Scheduling models.
Manages the conference programme: sessions, paper assignments, and keynote slots.
Supports in-person, online, and hybrid events.
"""
from django.db import models
from django.utils import timezone
from apps.accounts.models import User
import uuid


class Session(models.Model):
    """
    A scheduled block in the conference programme.
    Can be a paper presentation slot, workshop, keynote, panel, or ceremony.
    """

    SESSION_TYPES = [
        ('paper', 'Paper Presentation'),
        ('keynote', 'Keynote'),
        ('workshop', 'Workshop'),
        ('panel', 'Panel Discussion'),
        ('poster', 'Poster Session'),
        ('tutorial', 'Tutorial'),
        ('ceremony', 'Ceremony'),
        ('break', 'Break / Social'),
        ('other', 'Other'),
    ]

    FORMAT_CHOICES = [
        ('in_person', 'In-Person'),
        ('online', 'Online'),
        ('hybrid', 'Hybrid'),
    ]

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conference = models.ForeignKey(
        'conferences.Conference',
        on_delete=models.CASCADE,
        related_name='sessions'
    )
    track = models.ForeignKey(
        'conferences.ConferenceTrack',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='sessions'
    )
    chair = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='chaired_sessions',
        help_text="Session chair / moderator"
    )

    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    session_type = models.CharField(max_length=20, choices=SESSION_TYPES, default='paper')
    format = models.CharField(max_length=20, choices=FORMAT_CHOICES, default='in_person')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    # Timing
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    # Location
    room = models.CharField(max_length=200, blank=True, help_text="Room or hall name")
    location_notes = models.TextField(blank=True)
    online_link = models.URLField(blank=True, help_text="Zoom / Teams / Meet link for virtual sessions")
    capacity = models.PositiveIntegerField(null=True, blank=True)

    # Display
    order = models.PositiveSmallIntegerField(default=0, help_text="Display order within the day")
    is_public = models.BooleanField(default=True, help_text="Visible in public programme")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sessions'
        ordering = ['start_time', 'order']
        indexes = [
            models.Index(fields=['conference', 'status', 'start_time']),
            models.Index(fields=['conference', 'session_type']),
            models.Index(fields=['track', 'start_time']),
        ]

    def __str__(self):
        return f"{self.conference.short_name} — {self.title}"

    @property
    def duration_minutes(self):
        if self.start_time and self.end_time:
            return int((self.end_time - self.start_time).total_seconds() / 60)
        return None

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError("end_time must be after start_time.")


class SessionPresentation(models.Model):
    """
    Assigns an accepted paper (submission) to a session slot.
    Also supports keynote speakers and invited talks (no linked submission).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        Session,
        on_delete=models.CASCADE,
        related_name='presentations'
    )
    submission = models.ForeignKey(
        'submissions.Submission',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='session_presentations',
        help_text="Linked accepted paper (null for keynotes/invited talks)"
    )

    # For keynotes / invited speakers not in the system
    speaker_name = models.CharField(max_length=255, blank=True)
    speaker_email = models.EmailField(blank=True)
    speaker_bio = models.TextField(blank=True)
    speaker_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='presentations'
    )

    title = models.CharField(
        max_length=500, blank=True,
        help_text="Override title (defaults to submission title if linked)"
    )
    abstract = models.TextField(blank=True)

    # Slot timing within session
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Presentation slot length in minutes"
    )

    order = models.PositiveSmallIntegerField(default=0)
    is_confirmed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'session_presentations'
        ordering = ['session', 'order', 'start_time']
        indexes = [
            models.Index(fields=['session', 'order']),
            models.Index(fields=['submission']),
        ]

    def __str__(self):
        label = self.get_title()
        return f"{self.session.title} — {label}"

    def get_title(self):
        if self.title:
            return self.title
        if self.submission:
            return self.submission.title
        return self.speaker_name or "Untitled"

    def clean(self):
        from django.core.exceptions import ValidationError
        # A presentation must have either a linked submission or a speaker name
        if not self.submission and not self.speaker_name:
            raise ValidationError(
                "A presentation must have either a linked submission or a speaker name."
            )
        # Linked submission must be accepted
        if self.submission and self.submission.status not in ('accepted',):
            raise ValidationError(
                "Only accepted papers can be scheduled. "
                f"This submission status is '{self.submission.status}'."
            )
