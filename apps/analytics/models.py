"""
Analytics models.
Stores cached/exported reports generated for a conference.
All live stats are computed on-demand by AnalyticsService.
"""
from django.db import models
from apps.accounts.models import User
import uuid


class AnalyticsReport(models.Model):

    REPORT_TYPES = [
        ('overview', 'Conference Overview'),
        ('submissions', 'Submission Statistics'),
        ('reviews', 'Review Progress'),
        ('registrations', 'Registration Statistics'),
        ('attendance', 'Attendance Report'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conference = models.ForeignKey(
        'conferences.Conference',
        on_delete=models.CASCADE,
        related_name='analytics_reports'
    )
    report_type = models.CharField(max_length=30, choices=REPORT_TYPES)
    generated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='generated_reports'
    )
    data = models.JSONField(help_text="Computed report payload")
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'analytics_reports'
        ordering = ['-generated_at']
        indexes = [
            models.Index(fields=['conference', 'report_type']),
        ]

    def __str__(self):
        return f"{self.conference.short_name} — {self.get_report_type_display()} ({self.generated_at:%Y-%m-%d})"
