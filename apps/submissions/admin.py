"""Django admin for the Submissions app."""
from django.contrib import admin
from django import forms
from django.utils.html import format_html
from django.core.exceptions import ValidationError
from apps.submissions.models import Submission, SubmissionAuthor, SubmissionFile, SubmissionVersion
from apps.core.utils import upload_file_to_cloudinary


class SubmissionAuthorInline(admin.TabularInline):
    model = SubmissionAuthor
    extra = 0
    fields = ('name', 'email', 'affiliation', 'order', 'is_primary', 'is_corresponding')
    readonly_fields = ('is_primary',)


class SubmissionFileInline(admin.TabularInline):
    model = SubmissionFile
    extra = 0
    fields = ('file_type', 'original_filename', 'version_number', 'is_current', 'uploaded_by', 'uploaded_at')
    readonly_fields = ('uploaded_at',)


class SubmissionVersionInline(admin.TabularInline):
    model = SubmissionVersion
    extra = 0
    fields = ('version_number', 'title', 'changed_by', 'change_reason', 'created_at')
    readonly_fields = ('version_number', 'title', 'changed_by', 'change_reason', 'created_at')
    can_delete = False


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'conference', 'track', 'submitted_by',
        'status_badge', 'version_number', 'is_locked', 'submitted_at', 'created_at'
    )
    list_filter = ('status', 'is_locked', 'deadline_override', 'conference')
    search_fields = ('title', 'abstract', 'submitted_by__email', 'conference__title')
    readonly_fields = (
        'id', 'submitted_at', 'created_at', 'updated_at',
        'deadline_override_by', 'deadline_override_at', 'version_number',
        'decision_by', 'decision_at',
    )
    ordering = ('-created_at',)
    inlines = [SubmissionAuthorInline, SubmissionFileInline, SubmissionVersionInline]

    fieldsets = (
        ('Paper', {
            'fields': ('id', 'title', 'abstract', 'keywords')
        }),
        ('Conference', {
            'fields': ('conference', 'track')
        }),
        ('Status', {
            'fields': ('status', 'is_locked', 'version_number', 'submitted_by', 'submitted_at')
        }),
        ('Decision', {
            'fields': ('decision_note', 'decision_by', 'decision_at'),
            'classes': ('collapse',),
        }),
        ('Override', {
            'fields': (
                'deadline_override', 'deadline_override_reason',
                'deadline_override_by', 'deadline_override_at'
            ),
            'classes': ('collapse',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    actions = ['lock_submissions', 'unlock_submissions']

    def status_badge(self, obj):
        colours = {
            'draft': '#aaa',
            'submitted': '#3498db',
            'under_review': '#f39c12',
            'revision_requested': '#e67e22',
            'accepted': '#27ae60',
            'rejected': '#e74c3c',
            'withdrawn': '#95a5a6',
        }
        colour = colours.get(obj.status, '#aaa')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px">{}</span>',
            colour, obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def lock_submissions(self, request, queryset):
        updated = queryset.update(is_locked=True)
        self.message_user(request, f'{updated} submission(s) locked.')
    lock_submissions.short_description = 'Lock selected submissions'

    def unlock_submissions(self, request, queryset):
        updated = queryset.update(is_locked=False)
        self.message_user(request, f'{updated} submission(s) unlocked.')
    unlock_submissions.short_description = 'Unlock selected submissions'


@admin.register(SubmissionAuthor)
class SubmissionAuthorAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'submission', 'order', 'is_primary', 'is_corresponding')
    search_fields = ('name', 'email', 'submission__title')
    list_filter = ('is_primary', 'is_corresponding')


class SubmissionFileForm(forms.ModelForm):
    """
    Custom form for SubmissionFile with file upload support.
    """
    file = forms.FileField(
        required=False,
        help_text="Upload a new file. Leave empty to keep the current file."
    )

    class Meta:
        model = SubmissionFile
        fields = [
            'submission', 'file_type', 'file', 'version_number', 'is_current'
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
            # Check file size (10MB limit for submissions)
            max_size = 10 * 1024 * 1024  # 10MB
            if file.size > max_size:
                raise ValidationError("File size must be less than 10MB.")
        return file

    def clean(self):
        """Validate file type."""
        cleaned_data = super().clean()
        file = cleaned_data.get('file')
        
        if file:
            # Check file type based on model validation
            allowed_types = SubmissionFile.DOCUMENT_MIME_TYPES | SubmissionFile.IMAGE_MIME_TYPES | SubmissionFile.AUDIO_MIME_TYPES | SubmissionFile.VIDEO_MIME_TYPES
            if file.content_type not in allowed_types:
                raise ValidationError(
                    f"File type {file.content_type} is not allowed. "
                    f"Allowed types: {', '.join(sorted(allowed_types))}"
                )

        return cleaned_data

    def save(self, commit=True):
        """Handle file upload to Cloudinary."""
        instance = super().save(commit=False)
        file = self.cleaned_data.get('file')

        if file:
            # Upload file to Cloudinary
            try:
                result = upload_file_to_cloudinary(
                    file,
                    folder=f"submissions/{instance.submission.conference.short_name}/{instance.submission.id}",
                    public_id=f"{instance.file_type}_v{instance.version_number}_{file.name}",
                )

                # Update instance with upload results
                instance.file_url = result['url']
                instance.public_id = result.get('public_id', '')
                instance.original_filename = file.name
                instance.file_size = file.size
                instance.mime_type = file.content_type

            except Exception as e:
                raise ValidationError(f"Failed to upload file: {str(e)}")

        if commit:
            instance.save()
        return instance


@admin.register(SubmissionFile)
class SubmissionFileAdmin(admin.ModelAdmin):
    form = SubmissionFileForm

    list_display = ('original_filename', 'submission', 'file_type', 'version_number', 'is_current', 'uploaded_at')
    list_filter = ('file_type', 'is_current')
    search_fields = ('original_filename', 'submission__title')

    fieldsets = (
        ('File Information', {
            'fields': ('submission', 'file_type', 'file', 'version_number', 'is_current')
        }),
        ('File Metadata', {
            'fields': ('original_filename', 'file_size', 'mime_type', 'public_id'),
            'classes': ('collapse',)
        }),
        ('Upload Information', {
            'fields': ('uploaded_by', 'uploaded_at'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ('uploaded_at', 'file_size', 'mime_type', 'public_id', 'original_filename')

    def save_model(self, request, obj, form, change):
        """Set uploaded_by when creating new files."""
        if not change:  # Only for new objects
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(SubmissionVersion)
class SubmissionVersionAdmin(admin.ModelAdmin):
    list_display = ('submission', 'version_number', 'changed_by', 'change_reason', 'created_at')
    search_fields = ('submission__title', 'change_reason')
    readonly_fields = ('created_at',)
