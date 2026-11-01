"""Django admin for communications."""
from django.contrib import admin
from django.utils import timezone
from apps.communications.models import Announcement, Notification


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'conference', 'author', 'is_published', 'published_at', 'created_at')
    list_filter = ('is_published', 'conference')
    search_fields = ('title', 'content', 'conference__title', 'author__email')
    readonly_fields = ('created_at', 'updated_at', 'published_at')
    ordering = ('-created_at',)
    actions = ['publish_announcements', 'unpublish_announcements']

    def publish_announcements(self, request, queryset):
        updated = queryset.filter(is_published=False).update(
            is_published=True, published_at=timezone.now()
        )
        self.message_user(request, f'{updated} announcement(s) published.')
    publish_announcements.short_description = 'Publish selected announcements'

    def unpublish_announcements(self, request, queryset):
        updated = queryset.filter(is_published=True).update(
            is_published=False, published_at=None
        )
        self.message_user(request, f'{updated} announcement(s) unpublished.')
    unpublish_announcements.short_description = 'Unpublish selected announcements'


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'notification_type', 'title', 'priority', 'is_read', 'is_email_sent', 'created_at')
    list_filter = ('notification_type', 'priority', 'is_read', 'is_email_sent')
    search_fields = ('recipient__email', 'title', 'message')
    readonly_fields = ('created_at', 'read_at', 'email_sent_at', 'content_type', 'object_id')
    ordering = ('-created_at',)
    actions = ['mark_as_read', 'mark_as_unread']

    def mark_as_read(self, request, queryset):
        updated = queryset.filter(is_read=False).update(
            is_read=True, read_at=timezone.now()
        )
        self.message_user(request, f'{updated} notification(s) marked as read.')
    mark_as_read.short_description = 'Mark selected as read'

    def mark_as_unread(self, request, queryset):
        updated = queryset.filter(is_read=True).update(is_read=False, read_at=None)
        self.message_user(request, f'{updated} notification(s) marked as unread.')
    mark_as_unread.short_description = 'Mark selected as unread'
