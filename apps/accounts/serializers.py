"""
Serializers for User Authentication and Account Management
"""

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from django.contrib.auth import authenticate
from django.utils import timezone
from django.conf import settings
from apps.accounts.models import User, EmailVerificationToken, PasswordResetToken, UserProfile, UserAffiliation, UserProfileImage
from apps.core.utils import generate_secure_token, send_email_template
import uuid
from datetime import timedelta


class UserProfileNestedSerializer(serializers.Serializer):
    """Writable nested serializer for UserProfile fields."""
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    language = serializers.ChoiceField(choices=['en', 'es', 'fr', 'de'], required=False)
    prefer_email_notifications = serializers.BooleanField(required=False)
    prefer_sms_notifications = serializers.BooleanField(required=False)


class UserAffiliationNestedSerializer(serializers.Serializer):
    """Writable nested serializer for UserAffiliation fields."""
    institution = serializers.CharField(max_length=255, required=False, allow_blank=True)
    department = serializers.CharField(max_length=255, required=False, allow_blank=True)
    position = serializers.CharField(max_length=100, required=False, allow_blank=True)
    country = serializers.CharField(max_length=100, required=False, allow_blank=True)
    website = serializers.URLField(required=False, allow_blank=True)


class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer for user registration (sign-up).
    Creates a new user and triggers email verification.
    Optionally creates UserProfile and UserAffiliation if supplied.
    """

    password = serializers.CharField(
        write_only=True,
        min_length=8,
        error_messages={
            'required': 'Password is required.',
            'blank': 'Password cannot be blank.',
            'min_length': 'Password must be at least 8 characters long.',
        }
    )
    password_confirm = serializers.CharField(
        write_only=True,
        min_length=8,
    )
    role = serializers.ChoiceField(
        choices=['author', 'reviewer', 'organiser', 'participant'],
        required=False,
        allow_blank=True,
    )
    profile = UserProfileNestedSerializer(required=False)
    affiliation = UserAffiliationNestedSerializer(required=False)

    class Meta:
        model = User
        fields = [
            'email', 'first_name', 'last_name', 'bio',
            'password', 'password_confirm', 'role',
            'profile', 'affiliation',
        ]

    def validate(self, attrs):
        """Validate that passwords match."""
        password = attrs.get('password')
        password_confirm = attrs.pop('password_confirm', None)

        if password != password_confirm:
            raise serializers.ValidationError({'password': 'Passwords do not match.'})

        return attrs

    def validate_email(self, value):
        """Ensure email is unique."""
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError('An account with this email already exists.')
        return value

    def create(self, validated_data):
        """Create user and send email verification token."""
        role = validated_data.pop('role', None)
        password = validated_data.pop('password')
        profile_data = validated_data.pop('profile', None)
        affiliation_data = validated_data.pop('affiliation', None)

        user = User.objects.create_user(
            email=validated_data['email'],
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            bio=validated_data.get('bio', ''),
            password=password,
        )

        user.is_participant = True
        if role:
            setattr(user, f'is_{role}', True)
        user.save()

        if profile_data:
            UserProfile.objects.update_or_create(user=user, defaults=profile_data)

        if affiliation_data:
            UserAffiliation.objects.update_or_create(user=user, defaults=affiliation_data)

        # Create email verification token
        token = generate_secure_token()
        expires_at = timezone.now() + timedelta(hours=24)

        EmailVerificationToken.objects.create(
            user=user,
            token=token,
            expires_at=expires_at,
        )

        # Send verification email
        verification_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
        send_email_template(
            subject='Verify your K-Conference email',
            template_name='emails/verify_email.html',
            context={
                'user': user,
                'verification_url': verification_url,
                'expires_in_hours': 24,
            },
            recipient_list=[user.email],
        )

        return user


class EmailVerificationSerializer(serializers.Serializer):
    """
    Serializer for email verification.
    Takes a token and marks the user's email as verified.
    """
    
    token = serializers.CharField(required=True)
    
    def validate_token(self, value):
        """Validate the email verification token."""
        try:
            token_obj = EmailVerificationToken.objects.get(token=value)
        except EmailVerificationToken.DoesNotExist:
            raise serializers.ValidationError('Invalid verification token.')
        
        if not token_obj.is_valid():
            raise serializers.ValidationError('Token has expired or already been used.')
        
        return value
    
    def create(self, validated_data):
        """Mark email as verified."""
        token_obj = EmailVerificationToken.objects.get(token=validated_data['token'])
        token_obj.is_used = True
        token_obj.used_at = timezone.now()
        token_obj.save()
        
        token_obj.user.email_verified = True
        token_obj.user.email_verified_at = timezone.now()
        token_obj.user.save()
        
        return {'message': 'Email verified successfully.'}


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom JWT token serializer that includes user info.
    """
    
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    
    def validate(self, attrs):
        """Authenticate user and return tokens."""
        email = attrs.get('email')
        password = attrs.get('password')
        
        # Authenticate
        user = authenticate(request=self.context.get('request'), email=email, password=password)
        
        if not user:
            raise serializers.ValidationError('Invalid email or password.')
        
        if not user.is_active:
            raise serializers.ValidationError('This account is inactive.')
        
        if not user.email_verified:
            raise serializers.ValidationError('Email address is not verified.')
        
        # Update last login
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])
        
        # Get tokens
        refresh = self.get_token(user)
        
        return {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'id': str(user.id),
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'roles': {
                    'author': user.is_author,
                    'reviewer': user.is_reviewer,
                    'organiser': user.is_organiser,
                    'participant': user.is_participant,
                },
            }
        }


class PasswordResetRequestSerializer(serializers.Serializer):
    """
    Request a password reset token.
    Sends an email with reset link.
    """
    
    email = serializers.EmailField()
    
    def validate_email(self, value):
        """Check if user exists."""
        try:
            User.objects.get(email=value)
        except User.DoesNotExist:
            # Don't reveal if email exists for security
            pass
        return value
    
    def create(self, validated_data):
        """Generate and send password reset token."""
        try:
            user = User.objects.get(email=validated_data['email'])
            
            # Delete old tokens
            PasswordResetToken.objects.filter(user=user, is_used=False).delete()
            
            # Create new token
            token = generate_secure_token()
            expires_hours = settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS
            expires_at = timezone.now() + timedelta(hours=expires_hours)
            
            PasswordResetToken.objects.create(
                user=user,
                token=token,
                expires_at=expires_at,
                ip_address=self.context.get('request').META.get('REMOTE_ADDR', None),
            )
            
            # Send reset email
            reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
            send_email_template(
                subject='Reset your K-Conference password',
                template_name='emails/password_reset.html',
                context={
                    'user': user,
                    'reset_url': reset_url,
                    'expires_in_hours': expires_hours,
                },
                recipient_list=[user.email],
            )
        except User.DoesNotExist:
            pass  # Security: don't reveal if email exists
        
        return {'message': 'If an account exists, a reset link has been sent to the email.'}


class PasswordResetConfirmSerializer(serializers.Serializer):
    """
    Reset password using token.
    Validates token and updates password.
    """
    
    token = serializers.CharField(required=True)
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        error_messages={
            'min_length': 'Password must be at least 8 characters long.',
        }
    )
    password_confirm = serializers.CharField(write_only=True, min_length=8)
    
    def validate(self, attrs):
        """Validate token and passwords."""
        token = attrs.get('token')
        password = attrs.get('password')
        password_confirm = attrs.get('password_confirm')
        
        # Validate token
        try:
            token_obj = PasswordResetToken.objects.get(token=token)
        except PasswordResetToken.DoesNotExist:
            raise serializers.ValidationError({'token': 'Invalid reset token.'})
        
        if not token_obj.is_valid():
            raise serializers.ValidationError({'token': 'Token has expired or already been used.'})
        
        # Validate passwords match
        if password != password_confirm:
            raise serializers.ValidationError({'password': 'Passwords do not match.'})
        
        attrs['token_obj'] = token_obj
        return attrs
    
    def create(self, validated_data):
        """Update user password."""
        token_obj = validated_data['token_obj']
        user = token_obj.user
        
        # Set new password
        user.set_password(validated_data['password'])
        user.save()
        
        # Mark token as used
        token_obj.is_used = True
        token_obj.used_at = timezone.now()
        token_obj.save()
        
        return {'message': 'Password reset successfully. You can now log in with your new password.'}


class ChangePasswordSerializer(serializers.Serializer):
    """
    Change password for authenticated user.
    """
    
    current_password = serializers.CharField(write_only=True)
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        error_messages={
            'min_length': 'Password must be at least 8 characters long.',
        }
    )
    password_confirm = serializers.CharField(write_only=True, min_length=8)
    
    def validate_current_password(self, value):
        """Verify current password."""
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Current password is incorrect.')
        return value
    
    def validate(self, attrs):
        """Validate passwords match."""
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({'password': 'Passwords do not match.'})
        return attrs
    
    def create(self, validated_data):
        """Update password."""
        user = self.context['request'].user
        user.set_password(validated_data['password'])
        user.save()
        return {'message': 'Password changed successfully.'}


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating user profile.
    Accepts nested `profile` and `affiliation` objects to update related models.
    """

    roles = serializers.SerializerMethodField()
    profile_picture = serializers.SerializerMethodField()
    profile = UserProfileNestedSerializer(required=False)
    affiliation = UserAffiliationNestedSerializer(required=False)

    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'bio', 'profile_picture', 'roles', 'profile', 'affiliation']
        read_only_fields = ['id', 'email']

    def get_roles(self, obj):
        """Return user's roles."""
        return {
            'author': obj.is_author,
            'reviewer': obj.is_reviewer,
            'organiser': obj.is_organiser,
            'participant': obj.is_participant,
        }

    def get_profile_picture(self, obj):
        """Return profile picture URL."""
        if hasattr(obj, 'profile_image') and obj.profile_image:
            return obj.profile_image.image_url
        return None

    def update(self, instance, validated_data):
        profile_data = validated_data.pop('profile', None)
        affiliation_data = validated_data.pop('affiliation', None)

        # Update User fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update UserProfile
        if profile_data:
            from apps.accounts.models import UserProfile
            UserProfile.objects.update_or_create(
                user=instance,
                defaults=profile_data,
            )

        # Update UserAffiliation
        if affiliation_data:
            from apps.accounts.models import UserAffiliation
            UserAffiliation.objects.update_or_create(
                user=instance,
                defaults=affiliation_data,
            )

        return instance


from drf_spectacular.utils import extend_schema_field
from drf_spectacular.openapi import OpenApiTypes


@extend_schema_field(OpenApiTypes.BINARY)
class BinaryImageField(serializers.ImageField):
    """ImageField that Swagger renders as a file-picker instead of a URL input."""
    pass


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    """
    Admin-only serializer for updating a user's role flags and account status.
    Used by UserManagementViewSet (PATCH /api/v1/accounts/admin/users/{id}/).
    """
    profile = UserProfileNestedSerializer(required=False)
    affiliation = UserAffiliationNestedSerializer(required=False)

    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'bio',
            'is_author', 'is_reviewer', 'is_organiser', 'is_participant', 'is_admin',
            'is_active',
            'profile', 'affiliation',
        ]

    def update(self, instance, validated_data):
        profile_data = validated_data.pop('profile', None)
        affiliation_data = validated_data.pop('affiliation', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if profile_data:
            UserProfile.objects.update_or_create(user=instance, defaults=profile_data)

        if affiliation_data:
            UserAffiliation.objects.update_or_create(user=instance, defaults=affiliation_data)

        return instance


class ProfilePictureUploadSerializer(serializers.Serializer):
    """Upload or replace the authenticated user's profile picture."""
    image = BinaryImageField()


class UserDetailSerializer(serializers.ModelSerializer):
    """
    Detailed user serializer with full information.
    """
    
    roles = serializers.SerializerMethodField()
    profile = serializers.SerializerMethodField()
    affiliation = serializers.SerializerMethodField()
    profile_picture = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'bio', 'profile_picture',
            'roles', 'email_verified', 'is_active', 'created_at', 'updated_at',
            'profile', 'affiliation'
        ]
        read_only_fields = fields
    
    def get_roles(self, obj):
        return {
            'author': obj.is_author,
            'reviewer': obj.is_reviewer,
            'organiser': obj.is_organiser,
            'participant': obj.is_participant,
        }
    
    def get_profile_picture(self, obj):
        """Return profile picture URL."""
        if hasattr(obj, 'profile_image') and obj.profile_image:
            return obj.profile_image.image_url
        return None
    
    def get_profile(self, obj):
        if hasattr(obj, 'profile'):
            return {
                'phone': obj.profile.phone,
                'language': obj.profile.language,
            }
        return None
    
    def get_affiliation(self, obj):
        if hasattr(obj, 'affiliation'):
            return {
                'institution': obj.affiliation.institution,
                'department': obj.affiliation.department,
                'position': obj.affiliation.position,
                'country': obj.affiliation.country,
            }
        return None


class ResendVerificationEmailSerializer(serializers.Serializer):
    """
    Resend email verification token.
    """
    
    email = serializers.EmailField()
    
    def validate_email(self, value):
        """Check if user exists and email not verified."""
        try:
            user = User.objects.get(email=value)
            if user.email_verified:
                raise serializers.ValidationError('This email is already verified.')
        except User.DoesNotExist:
            raise serializers.ValidationError('No account found with this email.')
        return value
    
    def create(self, validated_data):
        """Generate and send new verification token."""
        user = User.objects.get(email=validated_data['email'])
        
        # Delete old tokens
        EmailVerificationToken.objects.filter(user=user, is_used=False).delete()
        
        # Create new token
        token = generate_secure_token()
        expires_at = timezone.now() + timedelta(hours=24)
        
        EmailVerificationToken.objects.create(
            user=user,
            token=token,
            expires_at=expires_at,
        )
        
        # Send verification email
        verification_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
        send_email_template(
            subject='Verify your K-Conference email',
            template_name='emails/verify_email.html',
            context={
                'user': user,
                'verification_url': verification_url,
                'expires_in_hours': 24,
            },
            recipient_list=[user.email],
        )
        
        return {'message': 'Verification email sent.'}
