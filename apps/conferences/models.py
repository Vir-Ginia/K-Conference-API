"""
Conference Management Models
Complete conference lifecycle management for K-Conference platform.
"""

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from apps.accounts.models import User
import uuid


class Conference(models.Model):
    """
    Main conference entity supporting in-person, online, and hybrid events.
    """

    # Status choices
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('open', 'Open for Submissions'),
        ('review', 'Under Review'),
        ('closed', 'Closed'),
        ('archived', 'Archived'),
    ]

    # Conference type
    TYPE_CHOICES = [
        ('in_person', 'In-Person'),
        ('online', 'Online'),
        ('hybrid', 'Hybrid'),
    ]

    # Core fields
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    short_name = models.CharField(max_length=50, unique=True, help_text="Unique identifier for URLs")
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    # Event details
    conference_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='hybrid')
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    timezone = models.CharField(max_length=50, default='UTC')

    # Location/Venue
    venue_name = models.CharField(max_length=255, blank=True)
    venue_address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    online_link = models.URLField(blank=True, help_text="Zoom/Teams link for online sessions")

    # Capacity and registration
    max_participants = models.PositiveIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(1)],
        help_text="Maximum number of participants (null = unlimited)"
    )
    current_participants = models.PositiveIntegerField(default=0)

    # Deadlines
    submission_deadline = models.DateTimeField(null=True, blank=True)
    review_deadline = models.DateTimeField(null=True, blank=True)
    registration_deadline = models.DateTimeField(null=True, blank=True)

    # Organiser and settings
    organiser = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='organised_conferences',
        limit_choices_to={'is_organiser': True}
    )

    # Conference settings
    allow_late_submissions = models.BooleanField(default=False)
    require_abstract = models.BooleanField(default=True)
    require_keywords = models.BooleanField(default=True)
    max_authors_per_paper = models.PositiveIntegerField(default=5)
    max_file_size_mb = models.PositiveIntegerField(default=10)

    # Rules and policies
    submission_rules = models.TextField(blank=True)
    review_policy = models.TextField(blank=True)
    code_of_conduct = models.TextField(blank=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'conferences'
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['status', 'start_date']),
            models.Index(fields=['organiser', 'status']),
            models.Index(fields=['short_name']),
        ]

    def __str__(self):
        return f"{self.title} ({self.short_name})"

    # ── Effective deadline helpers ────────────────────────────────────────────

    def get_effective_submission_deadline(self):
        """ConferenceDeadline(submission_close) takes precedence over submission_deadline field."""
        cd = self.deadlines.filter(deadline_type='submission_close', is_active=True).first()
        return cd.deadline_date if cd else self.submission_deadline

    def get_effective_review_deadline(self):
        """ConferenceDeadline(review_end) takes precedence over review_deadline field."""
        cd = self.deadlines.filter(deadline_type='review_end', is_active=True).first()
        return cd.deadline_date if cd else self.review_deadline

    def get_effective_registration_deadline(self):
        """ConferenceDeadline(registration_close) takes precedence over registration_deadline field."""
        cd = self.deadlines.filter(deadline_type='registration_close', is_active=True).first()
        return cd.deadline_date if cd else self.registration_deadline

    # ── Open/closed checks ────────────────────────────────────────────────────

    def is_open_for_submissions(self):
        """Check if conference is accepting submissions.
        ConferenceDeadline records (submission_open / submission_close) take
        precedence over the flat submission_deadline field when present.
        """
        if self.status not in ['open']:
            return False
        now = timezone.now()

        open_dl = self.deadlines.filter(deadline_type='submission_open', is_active=True).first()
        if open_dl and now < open_dl.deadline_date:
            return False  # window hasn't opened yet

        close_dl = self.deadlines.filter(deadline_type='submission_close', is_active=True).first()
        if close_dl:
            return now <= close_dl.deadline_date

        # Fall back to Conference.submission_deadline
        if self.submission_deadline and now > self.submission_deadline:
            return False
        return True

    def is_open_for_reviews(self):
        """Check if conference is in review phase.
        ConferenceDeadline records (review_start / review_end) take precedence
        over the flat review_deadline field when present.
        """
        if self.status != 'review':
            return False
        now = timezone.now()

        start_dl = self.deadlines.filter(deadline_type='review_start', is_active=True).first()
        if start_dl and now < start_dl.deadline_date:
            return False  # review window hasn't opened yet

        end_dl = self.deadlines.filter(deadline_type='review_end', is_active=True).first()
        if end_dl:
            return now <= end_dl.deadline_date

        # Fall back to Conference.review_deadline
        if self.review_deadline and now > self.review_deadline:
            return False
        return True

    def is_open_for_registration(self):
        """Check if conference is accepting registrations.
        ConferenceDeadline records (registration_open / registration_close) take
        precedence over the flat registration_deadline field when present.
        """
        if self.status not in ('open', 'review'):
            return False
        now = timezone.now()

        open_dl = self.deadlines.filter(deadline_type='registration_open', is_active=True).first()
        if open_dl and now < open_dl.deadline_date:
            return False  # registration window hasn't opened yet

        close_dl = self.deadlines.filter(deadline_type='registration_close', is_active=True).first()
        if close_dl:
            return now <= close_dl.deadline_date

        # Fall back to Conference.registration_deadline
        if self.registration_deadline and now > self.registration_deadline:
            return False
        return True

    def get_available_spots(self):
        """Get remaining participant spots."""
        if not self.max_participants:
            return None  # Unlimited
        return max(0, self.max_participants - self.current_participants)


class ConferenceTrack(models.Model):
    """
    Conference tracks/themes for organizing submissions.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conference = models.ForeignKey(
        Conference,
        on_delete=models.CASCADE,
        related_name='tracks'
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    short_name = models.CharField(max_length=50, help_text="Short identifier for the track")

    # Track chair
    chair = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='chaired_tracks',
        # limit_choices_to={'is_reviewer': True}
    )

    # Track settings
    max_submissions = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Maximum submissions for this track (null = unlimited)"
    )
    current_submissions = models.PositiveIntegerField(default=0)

    # Review settings
    min_reviews_per_paper = models.PositiveIntegerField(default=2)
    max_reviews_per_paper = models.PositiveIntegerField(default=4)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'conference_tracks'
        unique_together = ['conference', 'short_name']
        ordering = ['conference', 'name']
        indexes = [
            models.Index(fields=['conference', 'is_active']),
        ]

    def __str__(self):
        return f"{self.conference.short_name} - {self.name}"

    def get_available_slots(self):
        """Get remaining submission slots for this track."""
        if not self.max_submissions:
            return None  # Unlimited
        return max(0, self.max_submissions - self.current_submissions)


class ConferenceDeadline(models.Model):
    """
    Flexible deadline system for conferences.
    """

    DEADLINE_TYPES = [
        ('submission_open', 'Submission Opens'),
        ('submission_close', 'Submission Closes'),
        ('review_start', 'Review Period Starts'),
        ('review_end', 'Review Period Ends'),
        ('registration_open', 'Registration Opens'),
        ('registration_close', 'Registration Closes'),
        ('camera_ready', 'Camera Ready Deadline'),
        ('conference_start', 'Conference Starts'),
        ('conference_end', 'Conference Ends'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conference = models.ForeignKey(
        Conference,
        on_delete=models.CASCADE,
        related_name='deadlines'
    )
    deadline_type = models.CharField(max_length=30, choices=DEADLINE_TYPES)
    title = models.CharField(max_length=255, help_text="Human-readable title")
    description = models.TextField(blank=True)
    deadline_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    # Notification settings
    notify_before_days = models.PositiveIntegerField(
        default=7,
        help_text="Days before deadline to send notifications"
    )

    class Meta:
        db_table = 'conference_deadlines'
        unique_together = ['conference', 'deadline_type']
        ordering = ['conference', 'deadline_date']
        indexes = [
            models.Index(fields=['conference', 'deadline_type']),
            models.Index(fields=['deadline_date', 'is_active']),
        ]

    def __str__(self):
        return f"{self.conference.short_name} - {self.title}"

    def is_past(self):
        """Check if deadline has passed."""
        return timezone.now() > self.deadline_date

    def days_until(self):
        """Get days until deadline."""
        if self.is_past():
            return 0
        delta = self.deadline_date - timezone.now()
        return delta.days


class ConferenceRole(models.Model):
    """
    User roles within specific conferences.
    """

    ROLE_CHOICES = [
        ('organiser', 'Organiser'),
        ('track_chair', 'Track Chair'),
        ('reviewer', 'Reviewer'),
        ('participant', 'Participant'),
        ('keynote_speaker', 'Keynote Speaker'),
        ('sponsor', 'Sponsor'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conference = models.ForeignKey(
        Conference,
        on_delete=models.CASCADE,
        related_name='user_roles'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='conference_roles'
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)

    # Role-specific data
    track = models.ForeignKey(
        ConferenceTrack,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assigned_users',
        help_text="Track for track chairs"
    )

    # Status and permissions
    is_active = models.BooleanField(default=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assigned_roles'
    )

    class Meta:
        db_table = 'conference_roles'
        unique_together = ['conference', 'user', 'role']
        ordering = ['conference', 'role', 'user__last_name']
        indexes = [
            models.Index(fields=['conference', 'role', 'is_active']),
            models.Index(fields=['user', 'conference']),
        ]

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.role} ({self.conference.short_name})"


class ReviewRubric(models.Model):
    """
    Review rubric configuration for conferences.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conference = models.ForeignKey(
        Conference,
        on_delete=models.CASCADE,
        related_name='review_rubrics'
    )
    name = models.CharField(max_length=255, help_text="Name of the rubric")
    description = models.TextField(blank=True)

    # Rubric settings
    min_score = models.PositiveIntegerField(default=1)
    max_score = models.PositiveIntegerField(default=5)
    score_labels = models.JSONField(
        default=dict,
        help_text="Score labels, e.g., {'1': 'Poor', '5': 'Excellent'}"
    )

    # Criteria
    criteria = models.JSONField(
        default=list,
        help_text="List of criteria with weights, e.g., [{'name': 'Originality', 'weight': 0.3}, ...]"
    )

    # Metadata
    is_default = models.BooleanField(default=False, help_text="Default rubric for the conference")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'review_rubrics'
        unique_together = ['conference', 'name']
        indexes = [
            models.Index(fields=['conference', 'is_default']),
        ]

    def __str__(self):
        return f"{self.conference.short_name} - {self.name}"

    def get_total_weight(self):
        """Calculate total weight of all criteria."""
        return sum(criterion.get('weight', 0) for criterion in self.criteria)


class ConferenceMedia(models.Model):
    """
    Media files for conferences (banners, logos, promotional images).
    Supports multiple media types with cloud storage.
    """

    MEDIA_TYPES = [
        ('image', 'Image'),
        ('audio', 'Audio'),
        ('doc', 'Document'),
        ('video', 'Video'),
        ('other', 'Other'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, help_text="Media identifier (e.g., 'banner', 'logo', 'promo1')")
    conference = models.ForeignKey(
        Conference,
        on_delete=models.CASCADE,
        related_name='media_files'
    )

    # Media details
    mediatype = models.CharField(max_length=20, choices=MEDIA_TYPES, help_text="Type of media content")
    title = models.CharField(max_length=255, help_text="Display title for the media")
    description = models.TextField(blank=True)
    alt_text = models.CharField(max_length=255, blank=True, help_text="Alt text for accessibility")

    # File storage
    file_url = models.URLField(help_text="Cloud storage URL")
    public_id = models.CharField(max_length=255, help_text="Service-specific identifier for deletion")
    service = models.CharField(max_length=50, default='cloudinary', help_text="Cloud service provider")

    # File metadata
    file_size = models.PositiveIntegerField(help_text="File size in bytes")
    mime_type = models.CharField(max_length=100, help_text="MIME type (image/jpeg, etc.)")
    width = models.PositiveIntegerField(null=True, blank=True, help_text="Image width in pixels")
    height = models.PositiveIntegerField(null=True, blank=True, help_text="Image height in pixels")

    # Display settings
    is_featured = models.BooleanField(default=False, help_text="Featured on conference page")
    display_order = models.PositiveIntegerField(default=0, help_text="Display order for sorting")
    is_active = models.BooleanField(default=True)

    # Metadata
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='uploaded_conference_media'
    )

    class Meta:
        db_table = 'conference_media'
        ordering = ['conference', 'display_order', 'uploaded_at']
        indexes = [
            models.Index(fields=['conference', 'mediatype', 'is_active']),
            models.Index(fields=['conference', 'name']),
            models.Index(fields=['conference', 'is_featured']),
            models.Index(fields=['uploaded_by']),
        ]
        unique_together = ['conference', 'name']  # Prevent duplicate names per conference

    def __str__(self):
        return f"{self.conference.short_name} - {self.name} ({self.mediatype})"

    def save(self, *args, **kwargs):
        """Set featured flag automatically for banners."""
        if self.name == 'banner' and self.is_featured:
            # Ensure only one featured banner per conference
            ConferenceMedia.objects.filter(
                conference=self.conference,
                name='banner',
                is_featured=True
            ).exclude(id=self.id).update(is_featured=False)
        super().save(*args, **kwargs)

    def get_featured_banner(self):
        """Get the featured banner for a conference."""
        return ConferenceMedia.objects.filter(
            conference=self.conference,
            name='banner',
            is_featured=True,
            is_active=True
        ).first()

    @property
    def is_image(self):
        """Check if this is an image file."""
        return self.mediatype == 'image' or self.mime_type.startswith('image/')
