"""Django admin for the Scheduling app."""
from django.contrib import admin
from django.utils.html import format_html
from apps.scheduling.models import Session, SessionPresentation


class SessionPresentationInline(admin.TabularInline):
    model = SessionPresentation
    extra = 0
    fields = ('order', 'submission', 'speaker_name', 'duration_minutes', 'is_confirmed')
    show_change_link = True


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'conference', 'track', 'session_type',
        'format', 'status_badge', 'start_time', 'end_time', 'room', 'is_public'
    )
    list_filter = ('status', 'session_type', 'format', 'conference', 'is_public')
    search_fields = ('title', 'description', 'room', 'conference__title')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('conference', 'start_time', 'order')
    inlines = [SessionPresentationInline]

    fieldsets = (
        ('Session', {'fields': ('conference', 'track', 'title', 'description', 'session_type', 'format', 'status')}),
        ('Timing', {'fields': ('start_time', 'end_time', 'order')}),
        ('Location', {'fields': ('room', 'location_notes', 'online_link', 'capacity')}),
        ('Settings', {'fields': ('chair', 'is_public', 'created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    actions = ['publish_sessions', 'unpublish_sessions']

    def status_badge(self, obj):
        colours = {'draft': '#aaa', 'published': '#27ae60', 'cancelled': '#e74c3c'}
        colour = colours.get(obj.status, '#aaa')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px">{}</span>',
            colour, obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def publish_sessions(self, request, queryset):
        updated = queryset.filter(status='draft').update(status='published')
        self.message_user(request, f'{updated} session(s) published.')
    publish_sessions.short_description = 'Publish selected sessions'

    def unpublish_sessions(self, request, queryset):
        updated = queryset.filter(status='published').update(status='draft')
        self.message_user(request, f'{updated} session(s) unpublished.')
    unpublish_sessions.short_description = 'Unpublish selected sessions'


@admin.register(SessionPresentation)
class SessionPresentationAdmin(admin.ModelAdmin):
    list_display = ('get_title', 'session', 'order', 'duration_minutes', 'is_confirmed', 'created_at')
    list_filter = ('is_confirmed', 'session__conference')
    search_fields = ('title', 'speaker_name', 'submission__title', 'session__title')
    readonly_fields = ('created_at',)

    def get_title(self, obj):
        return obj.get_title()
    get_title.short_description = 'Title'
