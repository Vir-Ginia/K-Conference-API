"""Django admin for the Registrations app."""
from django.contrib import admin
from django.utils.html import format_html
from apps.registrations.models import Registration


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = (
        'participant', 'conference', 'ticket_type',
        'status_badge', 'checked_in', 'checked_in_at', 'registered_at'
    )
    list_filter = ('status', 'ticket_type', 'checked_in', 'conference')
    search_fields = ('participant__email', 'participant__first_name', 'conference__title')
    readonly_fields = ('registered_at', 'updated_at', 'qr_code', 'checked_in_at', 'reviewed_at')
    ordering = ('-registered_at',)

    fieldsets = (
        ('Registration', {'fields': ('conference', 'participant', 'ticket_type', 'status', 'notes')}),
        ('Organiser Review', {'fields': ('reviewed_by', 'reviewed_at', 'rejection_reason'), 'classes': ('collapse',)}),
        ('Check-In', {'fields': ('checked_in', 'checked_in_at', 'checked_in_by', 'qr_code'), 'classes': ('collapse',)}),
        ('Timestamps', {'fields': ('registered_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    actions = ['approve_registrations', 'reject_registrations']

    def status_badge(self, obj):
        colours = {
            'pending': '#f39c12', 'approved': '#27ae60', 'waitlisted': '#3498db',
            'rejected': '#e74c3c', 'cancelled': '#95a5a6', 'checked_in': '#8e44ad',
        }
        colour = colours.get(obj.status, '#aaa')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px">{}</span>',
            colour, obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def approve_registrations(self, request, queryset):
        from django.utils import timezone
        updated = queryset.filter(status__in=('pending', 'waitlisted')).update(
            status='approved', reviewed_by=request.user, reviewed_at=timezone.now()
        )
        self.message_user(request, f'{updated} registration(s) approved.')
    approve_registrations.short_description = 'Approve selected registrations'

    def reject_registrations(self, request, queryset):
        from django.utils import timezone
        updated = queryset.exclude(status__in=('cancelled', 'checked_in')).update(
            status='rejected', reviewed_by=request.user, reviewed_at=timezone.now()
        )
        self.message_user(request, f'{updated} registration(s) rejected.')
    reject_registrations.short_description = 'Reject selected registrations'
