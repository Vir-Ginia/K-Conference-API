"""Serializers for Communications app."""
from rest_framework import serializers
from django.utils import timezone
from apps.communications.models import Announcement, Notification, FAQItem


class NotificationSerializer(serializers.ModelSerializer):
    notification_type_display = serializers.CharField(
        source='get_notification_type_display', read_only=True
    )
    priority_display = serializers.CharField(
        source='get_priority_display', read_only=True
    )
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = Notification
        fields = [
            'id', 'notification_type', 'notification_type_display',
            'title', 'message', 'priority', 'priority_display',
            'is_read', 'read_at', 'is_email_sent', 'email_sent_at',
            'created_at', 'expires_at', 'is_expired',
        ]
        read_only_fields = fields


class AnnouncementListSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    conference_name = serializers.CharField(source='conference.title', read_only=True)

    class Meta:
        model = Announcement
        fields = [
            'id', 'title', 'conference', 'conference_name',
            'author_name', 'is_published', 'published_at', 'created_at',
        ]

    def get_author_name(self, obj):
        return obj.author.get_full_name() or obj.author.email


class AnnouncementDetailSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    conference_name = serializers.CharField(source='conference.title', read_only=True)

    class Meta:
        model = Announcement
        fields = [
            'id', 'title', 'content', 'conference', 'conference_name',
            'author', 'author_name', 'is_published', 'published_at',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['author', 'published_at', 'created_at', 'updated_at']

    def get_author_name(self, obj):
        return obj.author.get_full_name() or obj.author.email


class AnnouncementCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Announcement
        fields = ['title', 'content', 'conference']

    def validate_conference(self, conference):
        request = self.context['request']
        if not conference.organiser == request.user and not request.user.is_admin:
            raise serializers.ValidationError(
                "You are not the organiser of this conference."
            )
        return conference

    def create(self, validated_data):
        validated_data['author'] = self.context['request'].user
        return super().create(validated_data)


class AnnouncementUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Announcement
        fields = ['title', 'content']

    def validate(self, attrs):
        if self.instance and self.instance.is_published:
            raise serializers.ValidationError(
                "Published announcements cannot be edited. Unpublish first."
            )
        return attrs


class FAQItemSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = FAQItem
        fields = [
            'id', 'conference', 'question', 'answer', 'category',
            'order', 'is_published', 'created_by', 'created_by_name',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.email
        return None


class FAQItemCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = FAQItem
        fields = ['conference', 'question', 'answer', 'category', 'order']

    def validate_conference(self, conference):
        request = self.context['request']
        if not request.user.is_admin and conference.organiser != request.user:
            raise serializers.ValidationError("You are not the organiser of this conference.")
        return conference

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class FAQItemUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = FAQItem
        fields = ['question', 'answer', 'category', 'order']
