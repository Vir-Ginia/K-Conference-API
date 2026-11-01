"""
Views for User Authentication and Account Management
Implements registration, login, password reset, and profile management.
"""
import logging

from rest_framework.views import APIView

logger = logging.getLogger(__name__)
from rest_framework.response import Response
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import authenticate
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from drf_spectacular.utils import extend_schema
from apps.core.permissions import IsAdminOrSuperUser
from apps.accounts.models import User, EmailVerificationToken, PasswordResetToken
from apps.accounts.serializers import (
    UserRegistrationSerializer,
    EmailVerificationSerializer,
    CustomTokenObtainPairSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    ChangePasswordSerializer,
    UserProfileUpdateSerializer,
    AdminUserUpdateSerializer,
    UserDetailSerializer,
    ResendVerificationEmailSerializer,
    ProfilePictureUploadSerializer,
)


class EmailBackend(ModelBackend):
    """
    Custom authentication backend using email instead of username.
    """
    
    def authenticate(self, request, email=None, password=None, **kwargs):
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return None
        
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        
        return None


class UserRegistrationView(APIView):
    """
    POST: Register a new user
    Endpoint: POST /api/v1/auth/register/
    
    Returns:
    - 201: User created (check email for verification link)
    - 400: Validation error
    """
    
    permission_classes = [AllowAny]
    
    @extend_schema(
        request=UserRegistrationSerializer,
        description="Register a new user account"
    )
    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(
                {
                    'success': True,
                    'message': 'Account created successfully. Please check your email to verify your address.',
                    'user': {
                        'id': str(user.id),
                        'email': user.email,
                        'first_name': user.first_name,
                        'last_name': user.last_name,
                    }
                },
                status=status.HTTP_201_CREATED
            )
        return Response(
            {
                'success': False,
                'errors': serializer.errors
            },
            status=status.HTTP_400_BAD_REQUEST
        )


class EmailVerificationView(APIView):
    """
    POST: Verify email address with token
    Endpoint: POST /api/v1/auth/verify-email/
    
    Request body:
    {
        "token": "verification_token_from_email"
    }
    
    Returns:
    - 200: Email verified
    - 400: Invalid or expired token
    """
    
    permission_classes = [AllowAny]
    
    @extend_schema(
        request=EmailVerificationSerializer,
        description="Verify email address with token"
    )
    def post(self, request):
        serializer = EmailVerificationSerializer(data=request.data)
        if serializer.is_valid():
            result = serializer.save()
            return Response(
                {
                    'success': True,
                    'message': result['message']
                },
                status=status.HTTP_200_OK
            )
        return Response(
            {
                'success': False,
                'errors': serializer.errors
            },
            status=status.HTTP_400_BAD_REQUEST
        )


class ResendVerificationEmailView(APIView):
    """
    POST: Resend email verification token
    Endpoint: POST /api/v1/auth/resend-verification/
    
    Request body:
    {
        "email": "user@example.com"
    }
    
    Returns:
    - 200: Verification email sent
    - 400: Email already verified or not found
    """
    
    permission_classes = [AllowAny]
    
    @extend_schema(
        request=ResendVerificationEmailSerializer,
        description="Resend email verification token to user"
    )
    def post(self, request):
        serializer = ResendVerificationEmailSerializer(
            data=request.data,
            context={'request': request}
        )
        if serializer.is_valid():
            result = serializer.save()
            return Response(
                {
                    'success': True,
                    'message': result['message']
                },
                status=status.HTTP_200_OK
            )
        return Response(
            {
                'success': False,
                'errors': serializer.errors
            },
            status=status.HTTP_400_BAD_REQUEST
        )


class LoginView(TokenObtainPairView):
    """
    POST: Login with email and password
    Endpoint: POST /api/v1/auth/login/
    
    Request body:
    {
        "email": "user@example.com",
        "password": "securepassword"
    }
    
    Returns:
    - 200: Login successful with access and refresh tokens
    - 401: Invalid credentials
    """
    
    permission_classes = [AllowAny]
    serializer_class = CustomTokenObtainPairSerializer
    authentication_classes = []


class LogoutView(APIView):
    """
    POST: Logout (invalidate refresh token)
    Endpoint: POST /api/v1/auth/logout/
    
    Note: JWT tokens are stateless, but you can blacklist refresh tokens
    by sending them to this endpoint.
    
    Returns:
    - 200: Logout successful
    """
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            from rest_framework_simplejwt.tokens import RefreshToken
            refresh_token = request.data.get('refresh')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
        except Exception:
            pass
        return Response(
            {
                'success': True,
                'message': 'Logged out successfully.'
            },
            status=status.HTTP_200_OK
        )


class PasswordResetRequestView(APIView):
    """
    POST: Request a password reset
    Endpoint: POST /api/v1/auth/password-reset/
    
    Request body:
    {
        "email": "user@example.com"
    }
    
    Returns:
    - 200: If email exists, reset link sent (doesn't reveal if email exists)
    - 400: Validation error
    """
    
    permission_classes = [AllowAny]
    
    @extend_schema(
        request=PasswordResetRequestSerializer,
        description="Request a password reset token"
    )
    def post(self, request):
        serializer = PasswordResetRequestSerializer(
            data=request.data,
            context={'request': request}
        )
        if serializer.is_valid():
            result = serializer.save()
            return Response(
                {
                    'success': True,
                    'message': result['message']
                },
                status=status.HTTP_200_OK
            )
        return Response(
            {
                'success': False,
                'errors': serializer.errors
            },
            status=status.HTTP_400_BAD_REQUEST
        )


class PasswordResetConfirmView(APIView):
    """
    POST: Reset password with token
    Endpoint: POST /api/v1/auth/password-reset-confirm/
    
    Request body:
    {
        "token": "reset_token",
        "password": "newpassword",
        "password_confirm": "newpassword"
    }
    
    Returns:
    - 200: Password reset successful
    - 400: Invalid token or validation error
    """
    
    permission_classes = [AllowAny]
    
    @extend_schema(
        request=PasswordResetConfirmSerializer,
        description="Reset password with token"
    )
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if serializer.is_valid():
            result = serializer.save()
            return Response(
                {
                    'success': True,
                    'message': result['message']
                },
                status=status.HTTP_200_OK
            )
        return Response(
            {
                'success': False,
                'errors': serializer.errors
            },
            status=status.HTTP_400_BAD_REQUEST
        )


class ChangePasswordView(APIView):
    """
    POST: Change password for authenticated user
    Endpoint: POST /api/v1/auth/change-password/
    
    Requires: JWT authentication
    
    Request body:
    {
        "current_password": "oldpassword",
        "password": "newpassword",
        "password_confirm": "newpassword"
    }
    
    Returns:
    - 200: Password changed
    - 400: Validation error
    - 401: Not authenticated
    """
    
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        request=ChangePasswordSerializer,
        description="Change password for authenticated user"
    )
    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={'request': request}
        )
        if serializer.is_valid():
            result = serializer.save()
            return Response(
                {
                    'success': True,
                    'message': result['message']
                },
                status=status.HTTP_200_OK
            )
        return Response(
            {
                'success': False,
                'errors': serializer.errors
            },
            status=status.HTTP_400_BAD_REQUEST
        )


class UserProfileViewSet(viewsets.ViewSet):
    """
    ViewSet for user profile management.
    Endpoints:
    - GET /api/v1/accounts/me/ - Get current user profile
    - PATCH /api/v1/accounts/me/ - Update current user profile
    - GET /api/v1/accounts/{id}/ - Get other user's profile
    """
    
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        responses={200: UserDetailSerializer},
        description="Retrieve the current authenticated user's full profile.",
    )
    def get_current_user(self, request):
        """
        GET /api/v1/accounts/me/
        Returns the current authenticated user's detailed profile.
        """
        serializer = UserDetailSerializer(request.user)
        return Response(
            {
                'success': True,
                'data': serializer.data
            },
            status=status.HTTP_200_OK
        )
    
    @extend_schema(
        request=UserProfileUpdateSerializer,
        responses={200: UserProfileUpdateSerializer},
        description="Update the current user's profile, nested profile settings, and affiliation.",
    )
    def update_current_user(self, request):
        """
        PATCH /api/v1/accounts/me/
        Update the current user's profile.
        """
        user = request.user
        serializer = UserProfileUpdateSerializer(
            user,
            data=request.data,
            partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(
                {
                    'success': True,
                    'message': 'Profile updated successfully.',
                    'data': serializer.data
                },
                status=status.HTTP_200_OK
            )
        return Response(
            {
                'success': False,
                'errors': serializer.errors
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    def retrieve_user(self, request, pk=None):
        """
        GET /api/v1/accounts/{id}/
        Get a user's public profile.
        """
        try:
            user = User.objects.get(id=pk)
        except User.DoesNotExist:
            return Response(
                {
                    'success': False,
                    'error': 'User not found.'
                },
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Only show basic public info
        serializer = UserDetailSerializer(user)
        return Response(
            {
                'success': True,
                'data': serializer.data
            },
            status=status.HTTP_200_OK
        )


class ProfilePictureUploadView(APIView):
    """
    POST /api/v1/accounts/me/picture/
    Upload or replace the authenticated user's profile picture.
    Accepts multipart/form-data with an `image` field.
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        request={'multipart/form-data': ProfilePictureUploadSerializer},
        description="Upload or replace profile picture",
    )
    def post(self, request):
        serializer = ProfilePictureUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'success': False, 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        image_file = serializer.validated_data['image']
        user = request.user

        import cloudinary
        import cloudinary.uploader
        from django.conf import settings

        cfg = settings.CLOUDINARY_CONFIG
        if not cfg.get('cloud_name'):
            return Response(
                {'success': False, 'error': 'Cloudinary is not configured on this server.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        cloudinary.config(**cfg)
        try:
            result = cloudinary.uploader.upload(
                image_file,
                folder=f'k_conference/profile_pictures/{user.id}',
                public_id='avatar',
                overwrite=True,
                resource_type='image',
            )
        except Exception as e:
            logger.error('Cloudinary upload failed for user %s: %s', user.id, e)
            return Response(
                {'success': False, 'error': f'Image upload failed: {e}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        image_url = result['secure_url']
        public_id = result['public_id']
        service = 'cloudinary'

        from apps.accounts.models import UserProfileImage
        UserProfileImage.objects.update_or_create(
            user=user,
            defaults={'image_url': image_url, 'public_id': public_id, 'service': service},
        )

        return Response({
            'success': True,
            'message': 'Profile picture updated.',
            'image_url': image_url,
        }, status=status.HTTP_200_OK)

    def delete(self, request):
        """DELETE /api/v1/accounts/me/picture/ — remove profile picture."""
        from apps.accounts.models import UserProfileImage
        try:
            img = request.user.profile_image
            if img.service == 'cloudinary' and img.public_id:
                import cloudinary.uploader
                import cloudinary
                from django.conf import settings
                cloudinary.config(**settings.CLOUDINARY_CONFIG)
                cloudinary.uploader.destroy(img.public_id)
            img.delete()
        except UserProfileImage.DoesNotExist:
            pass
        return Response({'success': True, 'message': 'Profile picture removed.'}, status=status.HTTP_200_OK)


class UserManagementViewSet(viewsets.ModelViewSet):
    """
    ViewSet for admin user management.
    Allows admins and superusers to list, view, and edit all users.
    
    Endpoints:
    - GET /api/v1/accounts/admin/users/ - List all users (with filtering/searching)
    - GET /api/v1/accounts/admin/users/{id}/ - Get user details
    - PATCH /api/v1/accounts/admin/users/{id}/ - Update user
    - PUT /api/v1/accounts/admin/users/{id}/ - Update user
    """
    
    serializer_class = UserDetailSerializer
    permission_classes = [IsAdminOrSuperUser]
    queryset = User.objects.all().select_related('profile', 'affiliation', 'profile_image')
    
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = [
        'is_author', 'is_reviewer', 'is_organiser', 'is_participant', 
        'is_admin', 'is_active', 'email_verified', 'is_staff', 'is_superuser'
    ]
    search_fields = ['email', 'first_name', 'last_name', 'bio']
    ordering_fields = ['email', 'first_name', 'last_name', 'created_at', 'updated_at', 'last_login']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        if self.action in ['update', 'partial_update']:
            return AdminUserUpdateSerializer
        return UserDetailSerializer
    
    def list(self, request, *args, **kwargs):
        """List all users with filtering and searching."""
        return super().list(request, *args, **kwargs)
    
    def retrieve(self, request, *args, **kwargs):
        """Get detailed user information."""
        return super().retrieve(request, *args, **kwargs)
    
    def update(self, request, *args, **kwargs):
        """Update user information."""
        return super().update(request, *args, **kwargs)
    
    def partial_update(self, request, *args, **kwargs):
        """Partially update user information."""
        return super().partial_update(request, *args, **kwargs)


# URL patterns will define these as methods
def create_profile_urls(router):
    """Helper to register profile URLs"""
    from rest_framework.routers import SimpleRouter
    
    class UserProfileRouter(SimpleRouter):
        routes = [
            # Current user endpoints
        ]
