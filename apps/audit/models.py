"""
Audit Logging System
Logs all critical actions for compliance and debugging.
"""

from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from apps.accounts.models import User
import uuid
import json


class AuditLog(models.Model):
    """
    Comprehensive audit log for all critical system actions.
    Tracks: submissions, deadlines, reviews, decisions, overrides, auth actions.
    """
    
    ACTION_CHOICES = [
        # Auth / User
        ('user.created', 'User Created'),
        ('user.updated', 'User Updated'),
        ('user.deleted', 'User Deleted'),
        ('user.email_verified', 'Email Verified'),
        ('user.password_changed', 'Password Changed'),
        ('user.password_reset', 'Password Reset'),
        ('user.login', 'Login'),
        ('user.logout', 'Logout'),

        # Conference
        ('conference.created', 'Conference Created'),
        ('conference.updated', 'Conference Updated'),
        ('conference.published', 'Conference Published'),
        ('conference.closed', 'Conference Closed'),

        # Submissions
        ('submission.created', 'Submission Created'),
        ('submission.updated', 'Submission Updated'),
        ('submission.submitted', 'Submission Submitted'),
        ('submission.withdrawn', 'Submission Withdrawn'),
        ('submission.override', 'Submission Organiser Override'),
        ('submission.deleted', 'Submission Deleted'),
        ('submission.deadline_override', 'Submission Deadline Override'),
        ('submission.lock', 'Submission Locked'),

        # Reviews
        ('review.assigned', 'Review Assigned'),
        ('review.unassigned', 'Review Unassigned'),
        ('review.assignment.accepted', 'Review Assignment Accepted'),
        ('review.assignment.declined', 'Review Assignment Declined'),
        ('review.conflict_declared', 'Conflict of Interest Declared'),
        ('review.submitted', 'Review Submitted'),
        ('review.override', 'Review Organiser Override'),

        # Decisions
        ('review.decision.made', 'Decision Made'),
        ('review.decision.override', 'Decision Override'),
        ('review.decision.published', 'Decision Published'),

        # Registrations
        ('registration.created', 'Registration Created'),
        ('registration.approved', 'Registration Approved'),
        ('registration.rejected', 'Registration Rejected'),
        ('registration.cancelled', 'Registration Cancelled'),
        ('registration.checked_in', 'Participant Checked In'),

        # Schedule
        ('schedule.session.created', 'Session Created'),
        ('schedule.session.updated', 'Session Updated'),
        ('schedule.session.published', 'Session Published'),
        ('schedule.session.deleted', 'Session Deleted'),
        ('schedule.presentation.assigned', 'Presentation Assigned'),
        ('schedule.presentation.removed', 'Presentation Removed'),

        # Communications
        ('announcement.created', 'Announcement Created'),
        ('announcement.published', 'Announcement Published'),
        ('announcement.deleted', 'Announcement Deleted'),

        # Admin
        ('admin.action', 'Admin Action'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Action details
    action = models.CharField(max_length=50, choices=ACTION_CHOICES, db_index=True)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='audit_logs_created')
    
    # Generic object reference
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    object_id = models.CharField(max_length=36, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Changes
    old_values = models.JSONField(default=dict, blank=True)
    new_values = models.JSONField(default=dict, blank=True)
    
    # Metadata
    reason = models.TextField(blank=True)  # For overrides
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        db_table = 'audit_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['action', 'created_at']),
            models.Index(fields=['actor', 'created_at']),
            models.Index(fields=['content_type', 'object_id']),
        ]
    
    def __str__(self):
        return f"{self.action} by {self.actor.email if self.actor else 'System'} at {self.created_at}"


class AuditLogManager:
    """
    Helper class to simplify audit logging throughout the system.
    """
    
    @staticmethod
    def log(
        action: str,
        actor: User = None,
        obj=None,
        old_values: dict = None,
        new_values: dict = None,
        reason: str = '',
        ip_address: str = None,
        user_agent: str = None,
    ) -> AuditLog:
        """
        Log an audit event.
        
        Args:
            action: Action type (from ACTION_CHOICES)
            actor: User performing the action
            obj: Django model instance being affected
            old_values: Previous field values (for updates)
            new_values: New field values (for updates)
            reason: Reason for action (especially for overrides)
            ip_address: IP address of request
            user_agent: User agent string
        
        Returns:
            AuditLog instance
        """
        content_type = None
        object_id = None
        
        if obj:
            content_type = ContentType.objects.get_for_model(obj)
            object_id = str(obj.pk)
        
        audit = AuditLog.objects.create(
            action=action,
            actor=actor,
            content_type=content_type,
            object_id=object_id,
            old_values=old_values or {},
            new_values=new_values or {},
            reason=reason or '',
            ip_address=ip_address,
            user_agent=user_agent or '',
        )
        
        return audit
    
    @staticmethod
    def log_user_action(action: str, user: User, request=None, reason: str = '') -> AuditLog:
        """
        Log an action affecting a user.
        """
        ip_address = None
        user_agent = None
        
        if request:
            ip_address = request.META.get('REMOTE_ADDR')
            user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        return AuditLogManager.log(
            action=action,
            actor=user,
            obj=user,
            ip_address=ip_address,
            user_agent=user_agent,
            reason=reason,
        )
