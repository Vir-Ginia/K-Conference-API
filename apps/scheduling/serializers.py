"""Serializers for the Scheduling app."""
from rest_framework import serializers
from apps.scheduling.models import Session, SessionPresentation


class SessionPresentationSerializer(serializers.ModelSerializer):
    display_title = serializers.SerializerMethodField()
    submission_title = serializers.CharField(source='submission.title', read_only=True, default=None)

    class Meta:
        model = SessionPresentation
        fields = [
            'id', 'session', 'submission', 'submission_title',
            'speaker_name', 'speaker_email', 'speaker_bio', 'speaker_user',
            'title', 'display_title', 'abstract',
            'start_time', 'end_time', 'duration_minutes',
            'order', 'is_confirmed', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def get_display_title(self, obj):
        return obj.get_title()


class SessionPresentationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SessionPresentation
        fields = [
            'submission', 'speaker_name', 'speaker_email',
            'speaker_bio', 'speaker_user', 'title', 'abstract',
            'start_time', 'end_time', 'duration_minutes', 'order',
        ]

    def validate(self, attrs):
        if not attrs.get('submission') and not attrs.get('speaker_name'):
            raise serializers.ValidationError(
                "Either a linked submission or a speaker name is required."
            )
        return attrs


class SessionListSerializer(serializers.ModelSerializer):
    conference_name = serializers.CharField(source='conference.title', read_only=True)
    track_name = serializers.CharField(source='track.name', read_only=True, default=None)
    session_type_display = serializers.CharField(source='get_session_type_display', read_only=True)
    format_display = serializers.CharField(source='get_format_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    presentation_count = serializers.IntegerField(source='presentations.count', read_only=True)
    duration_minutes = serializers.IntegerField(read_only=True)
    chair_name = serializers.SerializerMethodField()

    class Meta:
        model = Session
        fields = [
            'id', 'title', 'conference', 'conference_name',
            'track', 'track_name', 'session_type', 'session_type_display',
            'format', 'format_display', 'status', 'status_display',
            'start_time', 'end_time', 'duration_minutes',
            'room', 'online_link', 'capacity',
            'chair', 'chair_name', 'presentation_count',
            'order', 'is_public',
        ]

    def get_chair_name(self, obj):
        if obj.chair:
            return obj.chair.get_full_name() or obj.chair.email
        return None


class SessionDetailSerializer(SessionListSerializer):
    presentations = SessionPresentationSerializer(many=True, read_only=True)

    class Meta(SessionListSerializer.Meta):
        fields = SessionListSerializer.Meta.fields + [
            'description', 'location_notes', 'presentations', 'created_at', 'updated_at',
        ]


class SessionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Session
        fields = [
            'conference', 'track', 'chair', 'title', 'description',
            'session_type', 'format', 'start_time', 'end_time',
            'room', 'location_notes', 'online_link', 'capacity',
            'order', 'is_public',
        ]

    def validate(self, attrs):
        start = attrs.get('start_time')
        end = attrs.get('end_time')
        if start and end and end <= start:
            raise serializers.ValidationError({"end_time": "end_time must be after start_time."})

        track = attrs.get('track')
        conference = attrs.get('conference')
        if track and track.conference != conference:
            raise serializers.ValidationError(
                {"track": "Track does not belong to the selected conference."}
            )
        return attrs


class SessionUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Session
        fields = [
            'track', 'chair', 'title', 'description',
            'session_type', 'format', 'start_time', 'end_time',
            'room', 'location_notes', 'online_link', 'capacity',
            'order', 'is_public',
        ]

    def validate(self, attrs):
        start = attrs.get('start_time', self.instance.start_time if self.instance else None)
        end = attrs.get('end_time', self.instance.end_time if self.instance else None)
        if start and end and end <= start:
            raise serializers.ValidationError({"end_time": "end_time must be after start_time."})
        return attrs


class SessionCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default='')


class SessionPresentationUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SessionPresentation
        fields = [
            'title', 'abstract', 'speaker_name', 'speaker_email',
            'speaker_bio', 'speaker_user',
            'start_time', 'end_time', 'duration_minutes',
            'order', 'is_confirmed',
        ]
