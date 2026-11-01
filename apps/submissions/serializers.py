"""Serializers for the Submissions app."""
import json
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.openapi import OpenApiTypes
from apps.submissions.models import Submission, SubmissionAuthor, SubmissionFile, SubmissionVersion


@extend_schema_field(OpenApiTypes.BINARY)
class BinaryFileField(serializers.FileField):
    """FileField that Swagger renders as a file-picker instead of a URL input."""
    pass


class SubmissionAuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubmissionAuthor
        fields = ['id', 'name', 'email', 'affiliation', 'order', 'is_primary', 'is_corresponding']
        read_only_fields = ['id', 'is_primary']


class SubmissionFileSerializer(serializers.ModelSerializer):
    file_type_display = serializers.CharField(source='get_file_type_display', read_only=True)
    file_size_kb = serializers.SerializerMethodField()
    media_category = serializers.CharField(read_only=True)

    class Meta:
        model = SubmissionFile
        fields = [
            'id', 'file_type', 'file_type_display', 'file_url',
            'original_filename', 'file_size', 'file_size_kb',
            'mime_type', 'media_category', 'version_number', 'is_current', 'uploaded_at',
        ]

    def get_file_size_kb(self, obj):
        return round(obj.file_size / 1024, 2) if obj.file_size else 0


class SubmissionVersionSerializer(serializers.ModelSerializer):
    changed_by_email = serializers.EmailField(source='changed_by.email', read_only=True)

    class Meta:
        model = SubmissionVersion
        fields = [
            'id', 'version_number', 'title', 'abstract', 'keywords',
            'changed_by_email', 'change_reason', 'created_at',
        ]


# ── List view (compact) ──────────────────────────────────────────────────────

class SubmissionListSerializer(serializers.ModelSerializer):
    conference_name = serializers.CharField(source='conference.title', read_only=True)
    track_name = serializers.CharField(source='track.name', read_only=True, default=None)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    submitted_by_email = serializers.EmailField(source='submitted_by.email', read_only=True)
    author_count = serializers.IntegerField(source='authors.count', read_only=True)

    class Meta:
        model = Submission
        fields = [
            'id', 'title', 'conference', 'conference_name',
            'track', 'track_name', 'status', 'status_display',
            'submitted_by_email', 'author_count', 'version_number',
            'is_locked', 'submitted_at', 'created_at',
        ]


# ── Detail view ──────────────────────────────────────────────────────────────

class SubmissionDetailSerializer(serializers.ModelSerializer):
    conference_name = serializers.CharField(source='conference.title', read_only=True)
    track_name = serializers.CharField(source='track.name', read_only=True, default=None)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    submitted_by_email = serializers.EmailField(source='submitted_by.email', read_only=True)
    authors = SubmissionAuthorSerializer(many=True, read_only=True)
    current_files = serializers.SerializerMethodField()
    is_editable = serializers.BooleanField(read_only=True)
    deadline_override_by_email = serializers.SerializerMethodField()

    class Meta:
        model = Submission
        fields = [
            'id', 'title', 'abstract', 'keywords',
            'conference', 'conference_name', 'track', 'track_name',
            'status', 'status_display', 'version_number', 'is_locked', 'is_editable',
            'submitted_by_email', 'authors', 'current_files',
            'deadline_override', 'deadline_override_reason',
            'deadline_override_by_email', 'deadline_override_at',
            'decision_note', 'decision_at',
            'submitted_at', 'created_at', 'updated_at',
        ]

    def get_current_files(self, obj):
        files = obj.files.filter(is_current=True)
        return SubmissionFileSerializer(files, many=True).data

    def get_deadline_override_by_email(self, obj):
        if obj.deadline_override_by:
            return obj.deadline_override_by.email
        return None


# ── Create ───────────────────────────────────────────────────────────────────

class SubmissionCreateSerializer(serializers.ModelSerializer):
    authors = SubmissionAuthorSerializer(many=True, required=False)
    file = BinaryFileField(required=False, write_only=True)
    file_type = serializers.ChoiceField(
        choices=SubmissionFile.FILE_TYPE_CHOICES,
        default='paper',
        write_only=True,
        required=False,
    )
    # Explicit ListField so multipart string values are handled before field-level validation
    keywords = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
    )

    class Meta:
        model = Submission
        fields = ['conference', 'track', 'title', 'abstract', 'keywords', 'authors', 'file', 'file_type']

    def validate_keywords(self, value):
        # multipart sends the whole list as a single JSON string — parse it
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (ValueError, TypeError):
                raise serializers.ValidationError("Keywords must be a valid JSON list of strings.")
        if not isinstance(value, list):
            raise serializers.ValidationError("Keywords must be a list of strings.")
        if any(not isinstance(k, str) for k in value):
            raise serializers.ValidationError("Each keyword must be a string.")
        return value

    def validate(self, attrs):
        conference = attrs.get('conference')
        track = attrs.get('track')
        if track and track.conference != conference:
            raise serializers.ValidationError(
                {"track": "This track does not belong to the selected conference."}
            )
        # Abstract required check
        if conference and conference.require_abstract and not attrs.get('abstract', '').strip():
            raise serializers.ValidationError({"abstract": "Abstract is required for this conference."})
        # Keywords required check
        if conference and conference.require_keywords and not attrs.get('keywords'):
            raise serializers.ValidationError({"keywords": "Keywords are required for this conference."})
        return attrs


# ── Update ───────────────────────────────────────────────────────────────────

class SubmissionUpdateSerializer(serializers.ModelSerializer):
    file = BinaryFileField(required=False, write_only=True)
    file_type = serializers.ChoiceField(
        choices=SubmissionFile.FILE_TYPE_CHOICES,
        default='paper',
        write_only=True,
        required=False,
    )
    keywords = serializers.ListField(
        child=serializers.CharField(),
        required=False,
    )

    class Meta:
        model = Submission
        fields = ['title', 'abstract', 'keywords', 'track', 'file', 'file_type']

    def validate_keywords(self, value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (ValueError, TypeError):
                raise serializers.ValidationError("Keywords must be a valid JSON list of strings.")
        if not isinstance(value, list):
            raise serializers.ValidationError("Keywords must be a list of strings.")
        return value

    def validate(self, attrs):
        # Swagger sends empty strings for unfilled optional fields — drop them
        # so a PATCH with only `file` doesn't fail title/abstract validation.
        return {k: v for k, v in attrs.items() if v != ''}


# ── Organiser override ────────────────────────────────────────────────────────

class SubmissionOverrideSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=500, required=False)
    abstract = serializers.CharField(required=False)
    keywords = serializers.ListField(child=serializers.CharField(), required=False)

    def validate_keywords(self, value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (ValueError, TypeError):
                raise serializers.ValidationError("Keywords must be a valid JSON list of strings.")
        return value

    reason = serializers.CharField(
        required=True,
        help_text="Mandatory reason for overriding a locked submission."
    )
    file = BinaryFileField(required=False)
    file_type = serializers.ChoiceField(
        choices=SubmissionFile.FILE_TYPE_CHOICES,
        default='paper',
        required=False,
    )

    def validate_reason(self, value):
        if not value.strip():
            raise serializers.ValidationError("Override reason cannot be blank.")
        return value
