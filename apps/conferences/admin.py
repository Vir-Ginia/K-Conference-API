"""
Django Admin Configuration for Conferences App
Comprehensive admin interface for conference management.
"""

from django.contrib import admin
from django.contrib.admin import TabularInline
from django import forms
from django.utils.html import format_html
from django.db.models import Q
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.conferences.models import (
    Conference, ConferenceTrack, ConferenceDeadline,
    ConferenceRole, ReviewRubric, ConferenceMedia
)
from apps.core.utils import upload_file_to_cloudinary


class ConferenceTrackInline(TabularInline):
    """Inline admin for conference tracks."""
    model = ConferenceTrack
    extra = 0
    fields = ['name', 'short_name', 'chair', 'is_active']
    show_change_link = True


class ConferenceDeadlineInline(TabularInline):
    """Inline admin for conference deadlines."""
    model = ConferenceDeadline
    extra = 0
    fields = ['deadline_type', 'title', 'deadline_date', 'is_active']
    ordering = ['deadline_date']


class ConferenceRoleInline(TabularInline):
    """Inline admin for conference roles."""
    model = ConferenceRole
    extra = 0
    fields = ['user', 'role', 'track', 'is_active']
    autocomplete_fields = ['user']


class ConferenceMediaInline(TabularInline):
    """Inline admin for conference media."""
    model = ConferenceMedia
    extra = 0
    fields = ['name', 'mediatype', 'title', 'is_featured', 'is_active', 'file_preview']
    readonly_fields = ['file_preview']
    show_change_link = True

    def file_preview(self, obj):
        if obj.file_url:
            if getattr(obj, 'is_image', False):
                return format_html('<img src="{}" style="max-height:50px;max-width:100px;" />', obj.file_url)
            return format_html('<a href="{}" target="_blank">View File</a>', obj.file_url)
        return '-'
    file_preview.short_description = 'Preview'


@admin.register(Conference)
class ConferenceAdmin(admin.ModelAdmin):
    """
    Comprehensive admin for conference management.
    """

    list_display = [
        'title', 'short_name', 'status_badge', 'conference_type',
        'start_date', 'organiser', 'current_participants',
        'is_open_for_submissions', 'is_open_for_registration'
    ]
    list_filter = [
        'status', 'conference_type', 'start_date', 'is_active',
        'allow_late_submissions', 'require_abstract'
    ]
    search_fields = ['title', 'short_name', 'description', 'organiser__email']
    ordering = ['-start_date']
    date_hierarchy = 'start_date'

    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'short_name', 'description', 'status', 'conference_type')
        }),
        ('Event Details', {
            'fields': ('start_date', 'end_date', 'timezone')
        }),
        ('Location', {
            'fields': ('venue_name', 'venue_address', 'city', 'country', 'online_link')
        }),
        ('Capacity & Registration', {
            'fields': ('max_participants', 'current_participants', 'registration_deadline')
        }),
        ('Submission Settings', {
            'fields': ('submission_deadline', 'allow_late_submissions', 'require_abstract',
                      'require_keywords', 'max_authors_per_paper', 'max_file_size_mb')
        }),
        ('Review Settings', {
            'fields': ('review_deadline',)
        }),
        ('Organiser', {
            'fields': ('organiser',)
        }),
        ('Policies', {
            'fields': ('submission_rules', 'review_policy', 'code_of_conduct'),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_active', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ['created_at', 'updated_at', 'current_participants']
    inlines = [ConferenceTrackInline, ConferenceDeadlineInline, ConferenceRoleInline, ConferenceMediaInline]

    actions = [
        'mark_as_open', 'mark_as_review', 'mark_as_closed', 'mark_as_archived',
        'activate_conferences', 'deactivate_conferences'
    ]

    def status_badge(self, obj):
        """Display status with color coding."""
        colors = {
            'draft': 'gray',
            'open': 'green',
            'review': 'blue',
            'closed': 'orange',
            'archived': 'red'
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def is_open_for_submissions(self, obj):
        """Show if conference is accepting submissions."""
        return obj.is_open_for_submissions()
    is_open_for_submissions.boolean = True
    is_open_for_submissions.short_description = 'Open for Submissions'

    def is_open_for_registration(self, obj):
        """Show if conference is accepting registrations."""
        return obj.is_open_for_registration()
    is_open_for_registration.boolean = True
    is_open_for_registration.short_description = 'Open for Registration'

    @admin.action(description='Mark selected conferences as open')
    def mark_as_open(self, request, queryset):
        updated = queryset.update(status='open')
        self.message_user(request, f'{updated} conference(s) marked as open.')

    @admin.action(description='Mark selected conferences as under review')
    def mark_as_review(self, request, queryset):
        updated = queryset.update(status='review')
        self.message_user(request, f'{updated} conference(s) marked as under review.')

    @admin.action(description='Mark selected conferences as closed')
    def mark_as_closed(self, request, queryset):
        updated = queryset.update(status='closed')
        self.message_user(request, f'{updated} conference(s) marked as closed.')

    @admin.action(description='Mark selected conferences as archived')
    def mark_as_archived(self, request, queryset):
        updated = queryset.update(status='archived')
        self.message_user(request, f'{updated} conference(s) marked as archived.')

    @admin.action(description='Activate selected conferences')
    def activate_conferences(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} conference(s) activated.')

    @admin.action(description='Deactivate selected conferences')
    def deactivate_conferences(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} conference(s) deactivated.')


@admin.register(ConferenceTrack)
class ConferenceTrackAdmin(admin.ModelAdmin):
    """
    Admin for conference tracks.
    """

    list_display = [
        'name', 'conference', 'chair', 'current_submissions',
        'available_slots', 'is_active'
    ]
    list_filter = ['is_active', 'conference', 'chair']
    search_fields = ['name', 'short_name', 'description', 'conference__title']
    ordering = ['conference', 'name']

    fieldsets = (
        ('Track Information', {
            'fields': ('conference', 'name', 'short_name', 'description')
        }),
        ('Management', {
            'fields': ('chair', 'max_submissions', 'current_submissions')
        }),
        ('Review Settings', {
            'fields': ('min_reviews_per_paper', 'max_reviews_per_paper')
        }),
        ('Status', {
            'fields': ('is_active', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ['created_at', 'updated_at', 'current_submissions']

    def available_slots(self, obj):
        """Show available submission slots."""
        slots = obj.get_available_slots()
        return slots if slots is not None else 'Unlimited'
    available_slots.short_description = 'Available Slots'


@admin.register(ConferenceDeadline)
class ConferenceDeadlineAdmin(admin.ModelAdmin):
    """
    Admin for conference deadlines.
    """

    list_display = [
        'title', 'conference', 'deadline_type', 'deadline_date',
        'days_until', 'is_past', 'is_active'
    ]
    list_filter = ['deadline_type', 'is_active', 'conference']
    search_fields = ['title', 'description', 'conference__title']
    ordering = ['deadline_date']
    date_hierarchy = 'deadline_date'

    fieldsets = (
        ('Deadline Information', {
            'fields': ('conference', 'deadline_type', 'title', 'description')
        }),
        ('Timing', {
            'fields': ('deadline_date', 'notify_before_days')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
    )

    def days_until(self, obj):
        """Show days until deadline."""
        days = obj.days_until()
        if days == 0 and not obj.is_past():
            return 'Today'
        elif obj.is_past():
            return f'{-days} days ago'
        else:
            return f'{days} days'
    days_until.short_description = 'Days Until'

    def is_past(self, obj):
        """Show if deadline has passed."""
        return obj.is_past()
    is_past.boolean = True


@admin.register(ConferenceRole)
class ConferenceRoleAdmin(admin.ModelAdmin):
    """
    Admin for conference user roles.
    """

    list_display = [
        'user', 'conference', 'role', 'track', 'is_active', 'assigned_at'
    ]
    list_filter = ['role', 'is_active', 'conference', 'assigned_at']
    search_fields = ['user__email', 'user__first_name', 'user__last_name', 'conference__title']
    ordering = ['-assigned_at']
    date_hierarchy = 'assigned_at'
    autocomplete_fields = ['user', 'assigned_by']

    fieldsets = (
        ('Role Assignment', {
            'fields': ('conference', 'user', 'role', 'track')
        }),
        ('Management', {
            'fields': ('is_active', 'assigned_at', 'assigned_by')
        }),
    )

    readonly_fields = ['assigned_at']


@admin.register(ReviewRubric)
class ReviewRubricAdmin(admin.ModelAdmin):
    """
    Admin for review rubrics.
    """

    list_display = [
        'name', 'conference', 'is_default', 'total_weight', 'is_active'
    ]
    list_filter = ['is_default', 'is_active', 'conference']
    search_fields = ['name', 'description', 'conference__title']
    ordering = ['conference', '-is_default', 'name']

    fieldsets = (
        ('Rubric Information', {
            'fields': ('conference', 'name', 'description', 'is_default')
        }),
        ('Scoring', {
            'fields': ('min_score', 'max_score', 'score_labels')
        }),
        ('Criteria', {
            'fields': ('criteria',)
        }),
        ('Status', {
            'fields': ('is_active', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ['created_at', 'updated_at']

    def total_weight(self, obj):
        return f"{obj.get_total_weight():.2f}"
    total_weight.short_description = 'Total Weight'


class ConferenceMediaForm(forms.ModelForm):
    """
    Custom form for ConferenceMedia with file upload support.
    """
    file = forms.FileField(
        required=False,
        help_text="Upload a new file. Leave empty to keep the current file."
    )

    class Meta:
        model = ConferenceMedia
        fields = [
            'conference', 'name', 'mediatype', 'title', 'description', 'alt_text',
            'file', 'is_featured', 'display_order', 'is_active'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make file field required only for new instances
        if not self.instance.pk:
            self.fields['file'].required = True

    def clean_file(self):
        """Validate uploaded file size."""
        file = self.cleaned_data.get('file')
        if file:
            # Check file size (10MB limit)
            max_size = 10 * 1024 * 1024  # 10MB
            if file.size > max_size:
                raise ValidationError("File size must be less than 10MB.")
        return file

    def clean(self):
        """Validate file type based on mediatype."""
        cleaned_data = super().clean()
        file = cleaned_data.get('file')
        mediatype = cleaned_data.get('mediatype')
        
        if file and mediatype:
            allowed_types = {
                'image': ['image/jpeg', 'image/png', 'image/gif', 'image/webp'],
                'audio': ['audio/mpeg', 'audio/wav', 'audio/ogg', 'audio/mp4'],
                'doc': ['application/pdf', 'application/msword', 
                       'application/vnd.openxmlformats-officedocument.wordprocessingml.document'],
                'video': ['video/mp4', 'video/webm', 'video/ogg'],
                'other': ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 
                         'application/pdf', 'video/mp4', 'video/webm']
            }

            if mediatype in allowed_types and file.content_type not in allowed_types[mediatype]:
                raise ValidationError(
                    f"File type {file.content_type} is not allowed for {mediatype} files. "
                    f"Allowed types: {', '.join(allowed_types[mediatype])}"
                )

        return cleaned_data

    def save(self, commit=True):
        """Handle file upload to Cloudinary."""
        instance = super().save(commit=False)
        file = self.cleaned_data.get('file')

        if file:
            # Upload file to Cloudinary
            try:
                upload_result = upload_file_to_cloudinary(
                    file,
                    folder=f'conferences/{instance.conference.short_name}/media'
                )

                # Update instance with upload results
                instance.file_url = upload_result['url']
                instance.public_id = upload_result['public_id']
                instance.service = 'cloudinary'
                instance.file_size = file.size
                instance.mime_type = file.content_type
                instance.width = upload_result.get('width')
                instance.height = upload_result.get('height')

            except Exception as e:
                raise ValidationError(f"Failed to upload file: {str(e)}")

        if commit:
            instance.save()
        return instance


@admin.register(ConferenceMedia)
class ConferenceMediaAdmin(admin.ModelAdmin):
    """
    Admin for conference media files.
    """

    form = ConferenceMediaForm

    list_display = [
        'title', 'conference', 'name', 'mediatype', 'file_preview',
        'is_featured', 'uploaded_by', 'uploaded_at', 'is_active'
    ]
    list_filter = ['mediatype', 'is_featured', 'is_active', 'conference', 'uploaded_at']
    search_fields = ['title', 'description', 'alt_text', 'name', 'conference__title']
    ordering = ['-uploaded_at']
    date_hierarchy = 'uploaded_at'

    fieldsets = (
        ('Media Information', {
            'fields': ('conference', 'name', 'mediatype', 'title', 'description', 'alt_text')
        }),
        ('File Upload', {
            'fields': ('file', 'public_id', 'service')
        }),
        ('File Metadata', {
            'fields': ('file_size', 'mime_type', 'width', 'height'),
            'classes': ('collapse',)
        }),
        ('Display Settings', {
            'fields': ('is_featured', 'display_order', 'is_active')
        }),
        ('Upload Information', {
            'fields': ('uploaded_by', 'uploaded_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ['uploaded_at', 'updated_at', 'file_size', 'mime_type', 'width', 'height', 'public_id', 'service']

    def save_model(self, request, obj, form, change):
        """Set uploaded_by when creating new media."""
        if not change:  # Only for new objects
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)

    def file_preview(self, obj):
        """Show file preview for images."""
        if obj.is_image and obj.file_url:
            return format_html('<img src="{}" style="max-height: 50px; max-width: 100px;" />', obj.file_url)
        elif obj.file_url:
            return format_html('<a href="{}" target="_blank">View File</a>', obj.file_url)
        return '-'
    file_preview.short_description = 'Preview'

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        return super().get_queryset(request).select_related('conference', 'uploaded_by')

