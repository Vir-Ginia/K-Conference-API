"""
Django Admin Configuration for Audit App
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Q
from apps.audit.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """
    Read-only admin for audit logs.
    Provides comprehensive audit trail visibility.
    """
    
    list_display = (
        'action_badge',
        'actor_display',
        'object_display',
        'reason_display',
        'ip_address',
        'created_at',
    )
    list_filter = (
        'action',
        'created_at',
        ('actor', admin.RelatedOnlyFieldListFilter),
    )
    search_fields = ('action', 'actor__email', 'reason', 'ip_address')
    ordering = ('-created_at',)
    readonly_fields = (
        'id',
        'action',
        'actor',
        'content_type',
        'object_id',
        'content_object',
        'old_values_display',
        'new_values_display',
        'reason',
        'ip_address',
        'user_agent',
        'created_at',
    )
    
    fieldsets = (
        ('Action Information', {
            'fields': ('id', 'action', 'created_at')
        }),
        ('Actor', {
            'fields': ('actor', 'ip_address', 'user_agent'),
            'classes': ('collapse',)
        }),
        ('Affected Object', {
            'fields': ('content_type', 'object_id', 'content_object')
        }),
        ('Changes', {
            'fields': ('old_values_display', 'new_values_display'),
            'classes': ('collapse',)
        }),
        ('Override Details', {
            'fields': ('reason',),
            'classes': ('collapse',)
        }),
    )
    
    # Make it read-only
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def action_badge(self, obj):
        """Display action with color coding."""
        action_type = obj.get_action_display()
        
        # Color coding based on action type
        if 'password' in obj.action or 'login' in obj.action or 'email' in obj.action:
            color = '#0066cc'  # Blue - Auth related
        elif 'override' in obj.action:
            color = '#ff9900'  # Orange - Override
        elif 'deleted' in obj.action:
            color = '#cc0000'  # Red - Delete
        elif 'created' in obj.action:
            color = '#00cc00'  # Green - Create
        else:
            color = '#666666'  # Gray - Other
        
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            action_type
        )
    action_badge.short_description = 'Action'
    
    def actor_display(self, obj):
        """Display actor with link to user."""
        if obj.actor:
            url = reverse('admin:accounts_user_change', args=[obj.actor.id])
            return format_html(
                '<a href="{}">{}</a>',
                url,
                obj.actor.email
            )
        return '—'
    actor_display.short_description = 'Actor'
    
    def object_display(self, obj):
        """Display affected object."""
        if obj.content_object:
            model_name = obj.content_type.name
            return f'{model_name} ({obj.object_id})'
        return '—'
    object_display.short_description = 'Affected Object'
    
    def reason_display(self, obj):
        """Display reason in expandable format."""
        if obj.reason:
            return obj.reason[:50] + '...' if len(obj.reason) > 50 else obj.reason
        return '—'
    reason_display.short_description = 'Reason'
    
    def old_values_display(self, obj):
        """Display old values in formatted JSON."""
        if obj.old_values:
            import json
            return format_html(
                '<pre>{}</pre>',
                json.dumps(obj.old_values, indent=2)
            )
        return '—'
    old_values_display.short_description = 'Previous Values'
    
    def new_values_display(self, obj):
        """Display new values in formatted JSON."""
        if obj.new_values:
            import json
            return format_html(
                '<pre>{}</pre>',
                json.dumps(obj.new_values, indent=2)
            )
        return '—'
    new_values_display.short_description = 'New Values'
    
    class Media:
        css = {
            'all': ('admin/css/audit_log.css',)
        }
