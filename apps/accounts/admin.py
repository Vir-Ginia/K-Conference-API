"""
Django Admin Configuration for Accounts App
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django import forms
from django.utils.html import format_html
from django.db.models import Q
from django.core.exceptions import ValidationError
from apps.accounts.models import (
    User,
    EmailVerificationToken,
    PasswordResetToken,
    UserProfile,
    UserAffiliation,
    UserProfileImage,
)
from apps.core.utils import upload_file_to_cloudinary


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Custom admin for User model with comprehensive management.
    """
    
    list_display = (
        'email',
        'get_full_name',
        'get_roles_display',
        'email_verified_badge',
        'is_active_badge',
        'created_at',
    )
    list_filter = (
        'is_author',
        'is_reviewer',
        'is_organiser',
        'is_participant',
        'is_active',
        'email_verified',
        'created_at',
    )
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Personal Information', {
            'fields': ('email', 'first_name', 'last_name', 'bio', 'get_profile_picture')
        }),
        ('Roles', {
            'fields': ('is_author', 'is_reviewer', 'is_organiser', 'is_participant', 'is_admin'),
            'description': 'A user can have multiple roles simultaneously.'
        }),
        ('Status', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'email_verified', 'email_verified_at')
        }),
        ('Permissions', {
            'fields': ('groups', 'user_permissions'),
            'classes': ('collapse',)
        }),
        ('Important Dates', {
            'fields': ('last_login', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at', 'last_login', 'email_verified_at', 'id', 'get_profile_picture', 'get_full_name', 'get_roles_display')
    
    actions = [
        'activate_users',
        'deactivate_users',
        'mark_email_verified',
        'mark_email_unverified',
    ]
    
    def get_full_name(self, obj):
        return obj.get_full_name()
    get_full_name.short_description = 'Full Name'
    
    def get_roles_display(self, obj):
        roles = []
        if obj.is_author:
            roles.append('Author')
        if obj.is_reviewer:
            roles.append('Reviewer')
        if obj.is_organiser:
            roles.append('Organiser')
        if obj.is_participant:
            roles.append('Participant')
        if obj.is_admin:
            roles.append('Admin')
        
        return ', '.join(roles) if roles else '—'
    get_roles_display.short_description = 'Roles'
    
    def email_verified_badge(self, obj):
        if obj.email_verified:
            return format_html(
                '<span style="color: green; font-weight: bold;">{} Verified</span>',
                '✓'
            )
        return format_html(
            '<span style="color: red;">{} Unverified</span>',
            '✗'
        )
    email_verified_badge.short_description = 'Email Status'
    
    def is_active_badge(self, obj):
        if obj.is_active:
            return format_html(
                '<span style="color: green; font-weight: bold;">{}</span>',
                'Active'
            )
        return format_html(
            '<span style="color: red;">{}</span>',
            'Inactive'
        )
    is_active_badge.short_description = 'Account Status'
    
    def get_profile_picture(self, obj):
        if hasattr(obj, 'profile_image') and obj.profile_image:
            return format_html(
                '<a href="{}" target="_blank">View Image</a>',
                obj.profile_image.image_url
            )
        return '—'
    get_profile_picture.short_description = 'Profile Picture'
    
    @admin.action(description='Activate selected users')
    def activate_users(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} user(s) activated.')
    
    @admin.action(description='Deactivate selected users')
    def deactivate_users(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} user(s) deactivated.')
    
    @admin.action(description='Mark email as verified')
    def mark_email_verified(self, request, queryset):
        from django.utils import timezone
        updated = queryset.update(
            email_verified=True,
            email_verified_at=timezone.now()
        )
        self.message_user(request, f'{updated} user(s) marked as verified.')
    
    @admin.action(description='Mark email as unverified')
    def mark_email_unverified(self, request, queryset):
        updated = queryset.update(email_verified=False, email_verified_at=None)
        self.message_user(request, f'{updated} user(s) marked as unverified.')


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    """
    Admin for email verification tokens.
    """
    
    list_display = ('user_email', 'is_valid_badge', 'created_at', 'expires_at')
    list_filter = ('is_used', 'created_at', 'expires_at')
    search_fields = ('user__email', 'token')
    ordering = ('-created_at',)
    readonly_fields = ('token', 'id', 'created_at', 'used_at')
    
    fieldsets = (
        ('Token Information', {
            'fields': ('id', 'user', 'token')
        }),
        ('Status', {
            'fields': ('is_used', 'used_at')
        }),
        ('Expiration', {
            'fields': ('created_at', 'expires_at')
        }),
    )
    
    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User Email'
    
    def is_valid_badge(self, obj):
        if obj.is_valid():
            return format_html(
                '<span style="color: green; font-weight: bold;">{} Valid</span>',
                '✓'
            )
        return format_html(
            '<span style="color: red;">{} Expired/Used</span>',
            '✗'
        )
    is_valid_badge.short_description = 'Status'


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    """
    Admin for password reset tokens.
    """
    
    list_display = ('user_email', 'is_valid_badge', 'ip_address', 'created_at', 'expires_at')
    list_filter = ('is_used', 'created_at', 'expires_at')
    search_fields = ('user__email', 'token', 'ip_address')
    ordering = ('-created_at',)
    readonly_fields = ('token', 'id', 'created_at', 'used_at')
    
    fieldsets = (
        ('Token Information', {
            'fields': ('id', 'user', 'token')
        }),
        ('Status', {
            'fields': ('is_used', 'used_at')
        }),
        ('Request Details', {
            'fields': ('ip_address', 'created_at', 'expires_at'),
            'classes': ('collapse',)
        }),
    )
    
    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User Email'
    
    def is_valid_badge(self, obj):
        if obj.is_valid():
            return format_html(
                '<span style="color: green; font-weight: bold;">{} Valid</span>',
                '✓'
            )
        return format_html(
            '<span style="color: red;">{} Expired/Used</span>',
            '✗'
        )
    is_valid_badge.short_description = 'Status'


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """
    Admin for user profiles.
    """
    
    list_display = ('user_email', 'phone', 'language', 'created_at')
    list_filter = ('language', 'prefer_email_notifications', 'prefer_sms_notifications', 'created_at')
    search_fields = ('user__email', 'phone')
    ordering = ('-created_at',)
    readonly_fields = ('id', 'created_at', 'updated_at')
    
    fieldsets = (
        ('User', {
            'fields': ('id', 'user')
        }),
        ('Contact', {
            'fields': ('phone',)
        }),
        ('Preferences', {
            'fields': ('prefer_email_notifications', 'prefer_sms_notifications')
        }),
        ('Language', {
            'fields': ('language',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User Email'


@admin.register(UserAffiliation)
class UserAffiliationAdmin(admin.ModelAdmin):
    """
    Admin for user affiliations.
    """
    
    list_display = ('user_email', 'institution', 'department', 'country', 'created_at')
    list_filter = ('country', 'created_at')
    search_fields = ('user__email', 'institution', 'department', 'country')
    ordering = ('-created_at',)
    readonly_fields = ('id', 'created_at', 'updated_at')
    
    fieldsets = (
        ('User', {
            'fields': ('id', 'user')
        }),
        ('Affiliation Information', {
            'fields': ('institution', 'department', 'position', 'country')
        }),
        ('Web Presence', {
            'fields': ('website',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User Email'


class UserProfileImageForm(forms.ModelForm):
    """
    Custom form for UserProfileImage with file upload support.
    """
    image = forms.ImageField(
        required=False,
        help_text="Upload a new profile image. Leave empty to keep the current image."
    )

    class Meta:
        model = UserProfileImage
        fields = ['user', 'image']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make image field required only for new instances
        if not self.instance.pk:
            self.fields['image'].required = True

    def clean_image(self):
        """Validate uploaded image."""
        image = self.cleaned_data.get('image')
        if image:
            # Check file size (5MB limit for profile images)
            max_size = 5 * 1024 * 1024  # 5MB
            if image.size > max_size:
                raise ValidationError("Image size must be less than 5MB.")

            # Check file type
            allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
            if image.content_type not in allowed_types:
                raise ValidationError(
                    f"Image type {image.content_type} is not allowed. "
                    f"Allowed types: {', '.join(allowed_types)}"
                )

        return image

    def save(self, commit=True):
        """Handle image upload to Cloudinary."""
        instance = super().save(commit=False)
        image = self.cleaned_data.get('image')

        if image:
            # Upload image to Cloudinary
            try:
                result = upload_file_to_cloudinary(
                    image,
                    folder=f"users/{instance.user.id}/profile",
                    public_id=f"profile_{instance.user.id}",
                )

                # Update instance with upload results
                instance.image_url = result['url']
                instance.public_id = result.get('public_id', '')
                instance.service = 'cloudinary'

            except Exception as e:
                raise ValidationError(f"Failed to upload image: {str(e)}")

        if commit:
            instance.save()
        return instance


@admin.register(UserProfileImage)
class UserProfileImageAdmin(admin.ModelAdmin):
    """
    Admin for user profile images.
    """
    
    form = UserProfileImageForm

    list_display = ('user_email', 'service', 'image_preview', 'uploaded_at')
    list_filter = ('service', 'uploaded_at')
    search_fields = ('user__email', 'public_id')
    ordering = ('-uploaded_at',)
    readonly_fields = ('id', 'uploaded_at', 'updated_at', 'public_id', 'service')
    
    fieldsets = (
        ('User', {
            'fields': ('id', 'user')
        }),
        ('Image Upload', {
            'fields': ('image',)
        }),
        ('Image Details', {
            'fields': ('public_id', 'service'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('uploaded_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User Email'
    
    def image_preview(self, obj):
        return format_html(
            '<a href="{}" target="_blank">View Image</a>',
            obj.image_url
        )
    image_preview.short_description = 'Image'
