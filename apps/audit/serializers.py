"""Serializers for the Audit app."""
from rest_framework import serializers
from apps.audit.models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source='actor.email', read_only=True, default=None)
    actor_name = serializers.SerializerMethodField()
    action_display = serializers.CharField(source='get_action_display', read_only=True)
    object_type = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            'id',
            'action',
            'action_display',
            'actor',
            'actor_email',
            'actor_name',
            'object_type',
            'object_id',
            'old_values',
            'new_values',
            'reason',
            'ip_address',
            'user_agent',
            'created_at',
        ]
        read_only_fields = fields

    def get_actor_name(self, obj):
        if obj.actor:
            return obj.actor.get_full_name() or obj.actor.email
        return None

    def get_object_type(self, obj):
        if obj.content_type:
            return obj.content_type.model
        return None
