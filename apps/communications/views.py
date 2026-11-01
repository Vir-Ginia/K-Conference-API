"""ViewSets for Communications app."""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes

from apps.communications.models import Announcement, Notification, FAQItem
from apps.communications.notification_service import notification_service
from apps.communications.serializers import (
    NotificationSerializer,
    AnnouncementListSerializer,
    AnnouncementDetailSerializer,
    AnnouncementCreateSerializer,
    AnnouncementUpdateSerializer,
    FAQItemSerializer,
    FAQItemCreateSerializer,
    FAQItemUpdateSerializer,
)
from apps.audit.models import AuditLogManager


class NotificationViewSet(viewsets.GenericViewSet):
    """
    User notification management.

    list            GET  /notifications/
    retrieve        GET  /notifications/{id}/
    destroy         DELETE /notifications/{id}/
    mark_read       POST /notifications/{id}/mark-read/
    mark_all_read   POST /notifications/mark-all-read/
    unread_count    GET  /notifications/unread-count/
    """
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Return notifications for the current user, excluding expired."""
        qs = Notification.objects.filter(recipient=self.request.user)

        is_read = self.request.query_params.get('is_read')
        if is_read is not None:
            qs = qs.filter(is_read=is_read.lower() == 'true')

        notification_type = self.request.query_params.get('type')
        if notification_type:
            qs = qs.filter(notification_type=notification_type)

        priority = self.request.query_params.get('priority')
        if priority:
            qs = qs.filter(priority=priority)

        include_expired = self.request.query_params.get('include_expired', 'false')
        if include_expired.lower() != 'true':
            qs = qs.exclude(
                expires_at__isnull=False,
                expires_at__lte=timezone.now()
            )

        return qs

    @extend_schema(
        parameters=[
            OpenApiParameter('is_read', OpenApiTypes.BOOL, description='Filter by read status'),
            OpenApiParameter('type', OpenApiTypes.STR, description='Filter by notification type'),
            OpenApiParameter('priority', OpenApiTypes.STR, description='Filter by priority (low, medium, high)'),
            OpenApiParameter('include_expired', OpenApiTypes.BOOL, description='Include expired notifications (default false)'),
        ],
        responses=NotificationSerializer(many=True),
    )
    def list(self, request):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        notification = get_object_or_404(
            Notification, pk=pk, recipient=request.user
        )
        serializer = self.get_serializer(notification)
        return Response(serializer.data)

    def destroy(self, request, pk=None):
        notification = get_object_or_404(
            Notification, pk=pk, recipient=request.user
        )
        notification.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='mark-read')
    def mark_read(self, request, pk=None):
        """Mark a single notification as read."""
        notification = get_object_or_404(
            Notification, pk=pk, recipient=request.user
        )
        notification.mark_as_read()
        serializer = self.get_serializer(notification)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='mark-all-read')
    def mark_all_read(self, request):
        """Mark all unread notifications as read."""
        count = notification_service.mark_notifications_read(request.user)
        return Response({
            'detail': f'{count} notification(s) marked as read.',
            'count': count,
        })

    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        """Get count of unread notifications."""
        count = notification_service.get_unread_count(request.user)
        return Response({'unread_count': count})


class AnnouncementViewSet(viewsets.GenericViewSet):
    """
    Conference announcement management.

    list        GET  /announcements/?conference={id}
    retrieve    GET  /announcements/{id}/
    create      POST /announcements/
    update      PUT/PATCH /announcements/{id}/
    destroy     DELETE /announcements/{id}/
    publish     POST /announcements/{id}/publish/
    unpublish   POST /announcements/{id}/unpublish/
    """
    queryset = Announcement.objects.all()
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Announcement.objects.select_related('conference', 'author')

        conference_id = self.request.query_params.get('conference')
        if conference_id:
            qs = qs.filter(conference_id=conference_id)

        # Organisers see all (draft + published); others see published only
        if not (user.is_organiser or user.is_admin):
            qs = qs.filter(is_published=True)

        return qs

    def get_serializer_class(self):
        if self.action == 'create':
            return AnnouncementCreateSerializer
        if self.action in ('update', 'partial_update'):
            return AnnouncementUpdateSerializer
        if self.action == 'list':
            return AnnouncementListSerializer
        return AnnouncementDetailSerializer

    def _is_conference_organiser(self, announcement):
        user = self.request.user
        return user.is_admin or announcement.conference.organiser == user

    @extend_schema(
        parameters=[OpenApiParameter('conference', OpenApiTypes.UUID, description='Filter by conference ID')],
        responses=AnnouncementListSerializer(many=True),
    )
    def list(self, request):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        announcement = get_object_or_404(self.get_queryset(), pk=pk)
        serializer = self.get_serializer(announcement)
        return Response(serializer.data)

    def create(self, request):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        announcement = serializer.save()
        AuditLogManager.log(
            action='announcement.created',
            actor=request.user,
            obj=announcement,
            new_values={'title': announcement.title, 'conference': announcement.conference.short_name},
        )
        return Response(
            AnnouncementDetailSerializer(announcement).data,
            status=status.HTTP_201_CREATED
        )

    def update(self, request, pk=None, partial=False):
        announcement = get_object_or_404(Announcement, pk=pk)
        if not self._is_conference_organiser(announcement):
            return Response(
                {'detail': 'Only the conference organiser can edit announcements.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = self.get_serializer(
            announcement, data=request.data, partial=partial, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        announcement = serializer.save()
        return Response(AnnouncementDetailSerializer(announcement).data)

    def partial_update(self, request, pk=None):
        return self.update(request, pk=pk, partial=True)

    def destroy(self, request, pk=None):
        announcement = get_object_or_404(Announcement, pk=pk)
        if not self._is_conference_organiser(announcement):
            return Response(
                {'detail': 'Only the conference organiser can delete announcements.'},
                status=status.HTTP_403_FORBIDDEN
            )
        AuditLogManager.log(
            action='announcement.deleted',
            actor=request.user,
            obj=announcement,
            new_values={'title': announcement.title},
        )
        announcement.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=None, responses=AnnouncementDetailSerializer)
    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        """Publish an announcement and notify all conference participants."""
        announcement = get_object_or_404(Announcement, pk=pk)
        if not self._is_conference_organiser(announcement):
            return Response(
                {'detail': 'Only the conference organiser can publish announcements.'},
                status=status.HTTP_403_FORBIDDEN
            )
        if announcement.is_published:
            return Response(
                {'detail': 'Announcement is already published.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        announcement.is_published = True
        announcement.published_at = timezone.now()
        announcement.save(update_fields=['is_published', 'published_at'])

        # Notify all active conference participants
        recipients = list(
            announcement.conference.user_roles.filter(is_active=True)
            .select_related('user')
            .values_list('user', flat=True)
        )
        if recipients:
            from apps.accounts.models import User as UserModel
            recipient_users = UserModel.objects.filter(id__in=recipients)
            notification_service.bulk_create_notifications(
                recipients=recipient_users,
                notification_type='announcement',
                title=f'New Announcement: {announcement.title}',
                message=announcement.content[:300],
                priority='medium',
                related_object=announcement,
                send_email=True,
            )

        AuditLogManager.log(
            action='announcement.published',
            actor=request.user,
            obj=announcement,
            new_values={'title': announcement.title, 'published_at': str(announcement.published_at)},
        )
        return Response(AnnouncementDetailSerializer(announcement).data)

    @extend_schema(request=None, responses=AnnouncementDetailSerializer)
    @action(detail=True, methods=['post'])
    def unpublish(self, request, pk=None):
        """Revert an announcement to draft."""
        announcement = get_object_or_404(Announcement, pk=pk)
        if not self._is_conference_organiser(announcement):
            return Response(
                {'detail': 'Only the conference organiser can unpublish announcements.'},
                status=status.HTTP_403_FORBIDDEN
            )
        if not announcement.is_published:
            return Response(
                {'detail': 'Announcement is not published.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        announcement.is_published = False
        announcement.published_at = None
        announcement.save(update_fields=['is_published', 'published_at'])
        return Response(AnnouncementDetailSerializer(announcement).data)


class FAQItemViewSet(viewsets.GenericViewSet):
    """
    FAQ / info area for a conference.

    Public (any authenticated user) can list and retrieve published items.
    Organisers can create, update, delete, publish, and unpublish items at any time.

    list        GET  /faq/?conference={id}
    retrieve    GET  /faq/{id}/
    create      POST /faq/
    update      PATCH /faq/{id}/
    destroy     DELETE /faq/{id}/
    publish     POST /faq/{id}/publish/
    unpublish   POST /faq/{id}/unpublish/
    """
    queryset = FAQItem.objects.all()
    serializer_class = FAQItemSerializer
    permission_classes = [IsAuthenticated]

    def _get_item(self, pk, organiser_only=False):
        """Fetch item, enforcing organiser-only access when requested."""
        if organiser_only:
            item = get_object_or_404(FAQItem, pk=pk)
            user = self.request.user
            if not user.is_admin and item.conference.organiser != user:
                return None, Response(
                    {'detail': 'Only the conference organiser can modify FAQ items.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            return item, None
        qs = FAQItem.objects.select_related('conference', 'created_by')
        user = self.request.user
        if not (user.is_organiser or user.is_admin):
            qs = qs.filter(is_published=True)
        return get_object_or_404(qs, pk=pk), None

    @extend_schema(
        parameters=[
            OpenApiParameter('conference', OpenApiTypes.UUID, description='Filter by conference ID'),
            OpenApiParameter('category', OpenApiTypes.STR, description='Filter by category name'),
        ],
        responses=FAQItemSerializer(many=True),
    )
    def list(self, request):
        user = request.user
        qs = FAQItem.objects.select_related('conference', 'created_by')

        conference_id = request.query_params.get('conference')
        if conference_id:
            qs = qs.filter(conference_id=conference_id)

        # Non-organisers only see published items
        if not (user.is_organiser or user.is_admin):
            qs = qs.filter(is_published=True)

        category = request.query_params.get('category')
        if category:
            qs = qs.filter(category__iexact=category)

        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(FAQItemSerializer(page, many=True).data)
        return Response(FAQItemSerializer(qs, many=True).data)

    def retrieve(self, request, pk=None):
        item, err = self._get_item(pk)
        if err:
            return err
        return Response(FAQItemSerializer(item).data)

    @extend_schema(request=FAQItemCreateSerializer, responses={201: FAQItemSerializer})
    def create(self, request):
        serializer = FAQItemCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        item = serializer.save()
        return Response(FAQItemSerializer(item).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=FAQItemUpdateSerializer, responses=FAQItemSerializer)
    def partial_update(self, request, pk=None):
        item, err = self._get_item(pk, organiser_only=True)
        if err:
            return err
        serializer = FAQItemUpdateSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        item = serializer.save()
        return Response(FAQItemSerializer(item).data)

    def destroy(self, request, pk=None):
        item, err = self._get_item(pk, organiser_only=True)
        if err:
            return err
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=None, responses=FAQItemSerializer)
    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        """Make an FAQ item visible to all conference participants."""
        item, err = self._get_item(pk, organiser_only=True)
        if err:
            return err
        if item.is_published:
            return Response({'detail': 'Already published.'}, status=status.HTTP_400_BAD_REQUEST)
        item.is_published = True
        item.save(update_fields=['is_published'])
        return Response(FAQItemSerializer(item).data)

    @extend_schema(request=None, responses=FAQItemSerializer)
    @action(detail=True, methods=['post'])
    def unpublish(self, request, pk=None):
        """Hide an FAQ item from participants."""
        item, err = self._get_item(pk, organiser_only=True)
        if err:
            return err
        if not item.is_published:
            return Response({'detail': 'Already unpublished.'}, status=status.HTTP_400_BAD_REQUEST)
        item.is_published = False
        item.save(update_fields=['is_published'])
        return Response(FAQItemSerializer(item).data)
