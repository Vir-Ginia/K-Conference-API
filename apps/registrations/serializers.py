"""Serializers for the Registrations app."""
from rest_framework import serializers
from apps.registrations.models import Registration


class RegistrationListSerializer(serializers.ModelSerializer):
    participant_email = serializers.EmailField(source='participant.email', read_only=True)
    participant_name = serializers.SerializerMethodField()
    conference_name = serializers.CharField(source='conference.title', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    ticket_type_display = serializers.CharField(source='get_ticket_type_display', read_only=True)

    class Meta:
        model = Registration
        fields = [
            'id', 'conference', 'conference_name',
            'participant', 'participant_email', 'participant_name',
            'status', 'status_display', 'ticket_type', 'ticket_type_display',
            'checked_in', 'checked_in_at', 'registered_at',
        ]

    def get_participant_name(self, obj):
        return obj.participant.get_full_name() or obj.participant.email


class RegistrationDetailSerializer(RegistrationListSerializer):
    reviewed_by_email = serializers.SerializerMethodField()
    qr_code = serializers.SerializerMethodField()

    class Meta(RegistrationListSerializer.Meta):
        fields = RegistrationListSerializer.Meta.fields + [
            'rejection_reason', 'reviewed_by_email', 'reviewed_at',
            'notes', 'qr_code', 'updated_at',
        ]

    def get_reviewed_by_email(self, obj):
        return obj.reviewed_by.email if obj.reviewed_by else None

    def get_qr_code(self, obj):
        """Expose QR token — view-level queryset already restricts to participant or organiser."""
        return obj.qr_code


class QRSerializer(serializers.ModelSerializer):
    conference_name = serializers.CharField(source='conference.title', read_only=True)
    participant_name = serializers.SerializerMethodField()
    ticket_type_display = serializers.CharField(source='get_ticket_type_display', read_only=True)

    class Meta:
        model = Registration
        fields = [
            'id', 'conference_name', 'participant_name',
            'ticket_type_display', 'status', 'qr_code',
        ]

    def get_participant_name(self, obj):
        return obj.participant.get_full_name() or obj.participant.email


class RegistrationCreateSerializer(serializers.ModelSerializer):
    ticket_type = serializers.ChoiceField(
        choices=Registration.TICKET_TYPE_CHOICES,
        default='standard',
        required=False,
    )

    class Meta:
        model = Registration
        fields = ['conference', 'ticket_type', 'notes']


class RegistrationRejectSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default='')


class QRCheckInSerializer(serializers.Serializer):
    qr_code = serializers.CharField()


class BulkStatusUpdateSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
        help_text="List of registration UUIDs to update.",
    )
    status = serializers.ChoiceField(
        choices=['approved', 'rejected'],
        help_text="Target status to apply to all listed registrations.",
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        default='',
        help_text="Optional reason (shown to participants when rejecting).",
    )
