"""
Registration models.
Handles participant registration, capacity management, waitlists, and attendance tracking.
"""
from django.db import models
from django.utils import timezone
from apps.accounts.models import User
import uuid


class Registration(models.Model):
    """
    A participant's registration for a conference.
    Supports approval/waitlist workflow and check-in tracking.
    """

    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('waitlisted', 'Waitlisted'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
        ('checked_in', 'Checked In'),
    ]

    TICKET_TYPE_CHOICES = [
        ('standard', 'Standard'),
        ('student', 'Student'),
        ('author', 'Author'),
        ('reviewer', 'Reviewer / Invited'),
        ('keynote', 'Keynote Speaker'),
        ('virtual', 'Virtual Attendee'),
        ('sponsor', 'Sponsor'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conference = models.ForeignKey(
        'conferences.Conference',
        on_delete=models.CASCADE,
        related_name='registrations'
    )
    participant = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='registrations'
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    ticket_type = models.CharField(max_length=20, choices=TICKET_TYPE_CHOICES, default='standard')

    # Organiser processing
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reviewed_registrations'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    # Check-in / attendance
    checked_in = models.BooleanField(default=False)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_in_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='check_ins_performed'
    )
    qr_code = models.CharField(
        max_length=255, blank=True, unique=True, null=True,
        help_text="Unique QR code token for event check-in"
    )

    # Participant notes (e.g., dietary/accessibility)
    notes = models.TextField(blank=True)

    registered_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'registrations'
        unique_together = [('conference', 'participant')]
        ordering = ['-registered_at']
        indexes = [
            models.Index(fields=['conference', 'status']),
            models.Index(fields=['participant', 'status']),
            models.Index(fields=['conference', 'checked_in']),
            models.Index(fields=['qr_code']),
        ]

    def __str__(self):
        return f"{self.participant.email} @ {self.conference.short_name} ({self.status})"

    @property
    def is_active(self):
        return self.status in ('approved', 'checked_in')
