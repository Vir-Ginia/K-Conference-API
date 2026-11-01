"""
Serializers for Conference Management
API serialization for conference entities and operations.
"""

from rest_framework import serializers
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.openapi import OpenApiTypes
from apps.conferences.models import (
    Conference, ConferenceTrack, ConferenceDeadline,
    ConferenceRole, ReviewRubric, ConferenceMedia
)
from apps.accounts.models import User



class ConferenceMediaSerializer(serializers.ModelSerializer):
    """
    Serializer for conference media files.
    """

    uploaded_by_name = serializers.CharField(source='uploaded_by.get_full_name', read_only=True)
    is_image = serializers.SerializerMethodField()

    class Meta:
        model = ConferenceMedia
        fields = [
            'id', 'name', 'mediatype', 'title', 'description', 'alt_text',
            'file_url', 'public_id', 'service', 'file_size', 'mime_type',
            'width', 'height', 'is_featured', 'display_order', 'is_active',
            'uploaded_at', 'updated_at', 'uploaded_by', 'uploaded_by_name',
            'is_image'
        ]
        read_only_fields = ['id', 'uploaded_at', 'updated_at', 'uploaded_by', 'uploaded_by_name']

    def get_is_image(self, obj):
        return obj.is_image

    def validate(self, data):
        """Ensure only one featured banner per conference."""
        if data.get('name') == 'banner' and data.get('is_featured'):
            existing_featured = ConferenceMedia.objects.filter(
                conference=data.get('conference') or self.instance.conference,
                name='banner',
                is_featured=True
            )
            if self.instance:
                existing_featured = existing_featured.exclude(id=self.instance.id)

            if existing_featured.exists():
                raise serializers.ValidationError(
                    "Only one featured banner is allowed per conference."
                )
        return data


class ConferenceTrackSerializer(serializers.ModelSerializer):
    """
    Serializer for conference tracks.
    """

    chair_name = serializers.CharField(source='chair.get_full_name', read_only=True)
    available_slots = serializers.SerializerMethodField()

    class Meta:
        model = ConferenceTrack
        fields = [
            'id', 'conference', 'name', 'description', 'short_name', 'chair', 'chair_name',
            'max_submissions', 'current_submissions', 'available_slots',
            'min_reviews_per_paper', 'max_reviews_per_paper',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'current_submissions', 'created_at', 'updated_at']

    def get_available_slots(self, obj):
        return obj.get_available_slots()


class ConferenceDeadlineSerializer(serializers.ModelSerializer):
    """
    Serializer for conference deadlines.
    """

    is_past = serializers.SerializerMethodField()
    days_until = serializers.SerializerMethodField()

    class Meta:
        model = ConferenceDeadline
        fields = [
            'id', 'conference', 'deadline_type', 'title', 'description', 'deadline_date',
            'notify_before_days', 'is_active', 'is_past', 'days_until'
        ]
        read_only_fields = ['id']

    def get_is_past(self, obj):
        return obj.is_past()

    def get_days_until(self, obj):
        return obj.days_until()


class ConferenceRoleSerializer(serializers.ModelSerializer):
    """
    Serializer for conference roles.
    """

    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    track_name = serializers.CharField(source='track.name', read_only=True)

    class Meta:
        model = ConferenceRole
        fields = [
            'id', 'conference', 'user', 'user_name', 'user_email', 'role', 'track', 'track_name',
            'is_active', 'assigned_at', 'assigned_by'
        ]
        read_only_fields = ['id', 'assigned_at', 'assigned_by']


class ReviewRubricSerializer(serializers.ModelSerializer):
    """
    Serializer for review rubrics.
    """

    total_weight = serializers.SerializerMethodField()

    class Meta:
        model = ReviewRubric
        fields = [
            'id', 'conference', 'name', 'description', 'min_score', 'max_score', 'score_labels',
            'criteria', 'is_default', 'is_active', 'total_weight', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'total_weight', 'created_at', 'updated_at']

    def get_total_weight(self, obj):
        return obj.get_total_weight()


class ConferenceListSerializer(serializers.ModelSerializer):
    """
    Serializer for conference listing (compact view).
    """

    organiser_name = serializers.CharField(source='organiser.get_full_name', read_only=True)
    is_open_for_submissions = serializers.SerializerMethodField()
    is_open_for_registration = serializers.SerializerMethodField()
    available_spots = serializers.SerializerMethodField()
    tracks_count = serializers.SerializerMethodField()

    class Meta:
        model = Conference
        fields = [
            'id', 'title', 'short_name', 'description', 'status', 'conference_type',
            'start_date', 'end_date', 'city', 'country', 'organiser_name',
            'is_open_for_submissions', 'is_open_for_registration', 'available_spots',
            'tracks_count', 'created_at'
        ]
        read_only_fields = fields

    def get_is_open_for_submissions(self, obj):
        return obj.is_open_for_submissions()

    def get_is_open_for_registration(self, obj):
        return obj.is_open_for_registration()

    def get_available_spots(self, obj):
        return obj.get_available_spots()

    def get_tracks_count(self, obj):
        return obj.tracks.filter(is_active=True).count()


class ConferenceDetailSerializer(serializers.ModelSerializer):
    """
    Detailed serializer for conference information.
    """

    organiser_name = serializers.CharField(source='organiser.get_full_name', read_only=True)
    organiser_email = serializers.CharField(source='organiser.email', read_only=True)
    tracks = ConferenceTrackSerializer(many=True, read_only=True)
    deadlines = ConferenceDeadlineSerializer(many=True, read_only=True)
    rubrics = ReviewRubricSerializer(source='review_rubrics', many=True, read_only=True)
    media = ConferenceMediaSerializer(source='media_files', many=True, read_only=True)

    # Status methods
    is_open_for_submissions = serializers.SerializerMethodField()
    is_open_for_reviews = serializers.SerializerMethodField()
    is_open_for_registration = serializers.SerializerMethodField()
    available_spots = serializers.SerializerMethodField()

    class Meta:
        model = Conference
        fields = [
            'id', 'title', 'short_name', 'description', 'status', 'conference_type',
            'start_date', 'end_date', 'timezone', 'venue_name', 'venue_address',
            'city', 'country', 'online_link', 'max_participants', 'current_participants',
            'submission_deadline', 'review_deadline', 'registration_deadline',
            'organiser', 'organiser_name', 'organiser_email',
            'allow_late_submissions', 'require_abstract', 'require_keywords',
            'max_authors_per_paper', 'max_file_size_mb',
            'submission_rules', 'review_policy', 'code_of_conduct',
            'tracks', 'deadlines', 'rubrics', 'media',
            'is_open_for_submissions', 'is_open_for_reviews', 'is_open_for_registration',
            'available_spots', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'current_participants', 'organiser_name', 'organiser_email',
            'tracks', 'deadlines', 'rubrics', 'media', 'created_at', 'updated_at'
        ]

    def get_is_open_for_submissions(self, obj):
        return obj.is_open_for_submissions()

    def get_is_open_for_reviews(self, obj):
        return obj.is_open_for_reviews()

    def get_is_open_for_registration(self, obj):
        return obj.is_open_for_registration()

    def get_available_spots(self, obj):
        return obj.get_available_spots()


class ConferenceCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating new conferences.
    """

    class Meta:
        model = Conference
        fields = [
            'title', 'short_name', 'description', 'conference_type',
            'start_date', 'end_date', 'timezone', 'venue_name', 'venue_address',
            'city', 'country', 'online_link', 'max_participants',
            'submission_deadline', 'review_deadline', 'registration_deadline',
            'allow_late_submissions', 'require_abstract', 'require_keywords',
            'max_authors_per_paper', 'max_file_size_mb',
            'submission_rules', 'review_policy', 'code_of_conduct'
        ]

    def validate_short_name(self, value):
        """Ensure short_name is unique."""
        if Conference.objects.filter(short_name=value).exists():
            raise serializers.ValidationError("A conference with this short name already exists.")
        return value

    def validate(self, attrs):
        """Cross-field date validation — all values are already parsed datetime objects here."""
        start_date = attrs.get('start_date')
        end_date = attrs.get('end_date')
        submission_deadline = attrs.get('submission_deadline')
        review_deadline = attrs.get('review_deadline')
        registration_deadline = attrs.get('registration_deadline')

        if start_date and end_date and end_date <= start_date:
            raise serializers.ValidationError({'end_date': 'End date must be after start date.'})

        if start_date and submission_deadline and submission_deadline >= start_date:
            raise serializers.ValidationError({'submission_deadline': 'Submission deadline must be before conference start.'})

        if start_date and review_deadline and review_deadline >= start_date:
            raise serializers.ValidationError({'review_deadline': 'Review deadline must be before conference start.'})

        if start_date and registration_deadline and registration_deadline >= start_date:
            raise serializers.ValidationError({'registration_deadline': 'Registration deadline must be before conference start.'})

        return attrs

    def create(self, validated_data):
        """Create conference with current user as organiser."""
        validated_data['organiser'] = self.context['request'].user
        return super().create(validated_data)


class ConferenceUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating conferences.
    """

    class Meta:
        model = Conference
        fields = [
            'title', 'description', 'status', 'conference_type',
            'start_date', 'end_date', 'timezone', 'venue_name', 'venue_address',
            'city', 'country', 'online_link', 'max_participants',
            'submission_deadline', 'review_deadline', 'registration_deadline',
            'allow_late_submissions', 'require_abstract', 'require_keywords',
            'max_authors_per_paper', 'max_file_size_mb', 'is_open_for_submissions', 'is_open_for_reviews', 'is_open_for_registration',  
            'submission_rules', 'review_policy', 'code_of_conduct', 'is_active'
        ]

    def validate(self, attrs):
        """Cross-field date validation — all values are already parsed datetime objects here."""
        instance = self.instance
        start_date = attrs.get('start_date', instance.start_date if instance else None)
        end_date = attrs.get('end_date', instance.end_date if instance else None)
        submission_deadline = attrs.get('submission_deadline', instance.submission_deadline if instance else None)
        review_deadline = attrs.get('review_deadline', instance.review_deadline if instance else None)
        registration_deadline = attrs.get('registration_deadline', instance.registration_deadline if instance else None)

        if start_date and end_date and end_date <= start_date:
            raise serializers.ValidationError({'end_date': 'End date must be after start date.'})

        if start_date and submission_deadline and submission_deadline >= start_date:
            raise serializers.ValidationError({'submission_deadline': 'Submission deadline must be before conference start.'})

        if start_date and review_deadline and review_deadline >= start_date:
            raise serializers.ValidationError({'review_deadline': 'Review deadline must be before conference start.'})

        if start_date and registration_deadline and registration_deadline >= start_date:
            raise serializers.ValidationError({'registration_deadline': 'Registration deadline must be before conference start.'})

        return attrs


@extend_schema_field(OpenApiTypes.BINARY)
class BinaryFileField(serializers.FileField):
    """FileField that Swagger renders as a file-picker instead of a URL input."""
    pass


class ConferenceMediaUploadSerializer(serializers.Serializer):
    """
    Serializer for uploading conference media files.
    """

    conference = serializers.UUIDField(required=True, help_text="Conference UUID")
    file = BinaryFileField(required=True)
    name = serializers.CharField(max_length=100, required=True, help_text="Media identifier (e.g., 'banner', 'logo')")
    mediatype = serializers.ChoiceField(
        choices=ConferenceMedia.MEDIA_TYPES,
        required=True
    )
    title = serializers.CharField(max_length=255, required=True)
    description = serializers.CharField(required=False, allow_blank=True)
    alt_text = serializers.CharField(max_length=255, required=False, allow_blank=True)
    is_featured = serializers.BooleanField(default=False)
    display_order = serializers.IntegerField(default=0, min_value=0)

    def validate_file(self, value):
        """Validate file type and size."""
        # Check file size (10MB limit for conference media)
        max_size = 10 * 1024 * 1024  # 10MB
        if value.size > max_size:
            raise serializers.ValidationError("File size must be less than 10MB.")

        # Check file type based on mediatype
        mediatype = self.initial_data.get('mediatype')
        allowed_types = {
            'image': ['image/jpeg', 'image/png', 'image/gif', 'image/webp'],
            'audio': ['audio/mpeg', 'audio/wav', 'audio/ogg', 'audio/mp4'],
            'doc': ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'],
            'video': ['video/mp4', 'video/webm', 'video/ogg'],
            'other': ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'application/pdf', 'video/mp4', 'video/webm']
        }

        if mediatype and hasattr(value, 'content_type'):
            if mediatype in allowed_types and value.content_type not in allowed_types[mediatype]:
                raise serializers.ValidationError(
                    f"File type {value.content_type} is not allowed for {mediatype} files. "
                    f"Allowed types: {', '.join(allowed_types[mediatype])}"
                )

        return value