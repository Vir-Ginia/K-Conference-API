"""ViewSet for the Audit app. Read-only. Admins see all; organisers see their conference's logs."""
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes

from apps.audit.models import AuditLog
from apps.audit.serializers import AuditLogSerializer


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only audit log access.

    Admins see all logs.
    Organisers see logs where the actor is themselves or any participant/reviewer/author
    within one of their conferences — scoped via conference query param.

    Filters (all optional, via query params):
      ?action=        — exact action code (e.g. review.submitted)
      ?actor=         — actor user ID
      ?object_type=   — model name (e.g. submission, review)
      ?object_id=     — UUID of the specific object
      ?date_from=     — ISO 8601 date (inclusive)
      ?date_to=       — ISO 8601 date (inclusive)
      ?search=        — free-text search across reason and actor email
    """
    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        if user.is_superuser or user.is_admin:
            qs = AuditLog.objects.select_related('actor', 'content_type').all()
        elif user.is_organiser:
            from apps.conferences.models import ConferenceRole
            from django.db.models import Q
            conf_user_ids = ConferenceRole.objects.filter(
                conference__organiser=user
            ).values_list('user_id', flat=True)
            qs = AuditLog.objects.select_related('actor', 'content_type').filter(
                Q(actor=user) | Q(actor_id__in=conf_user_ids)
            )
        else:
            return AuditLog.objects.none()

        params = self.request.query_params

        action = params.get('action')
        if action:
            qs = qs.filter(action=action)

        actor_id = params.get('actor')
        if actor_id:
            qs = qs.filter(actor_id=actor_id)

        object_type = params.get('object_type')
        if object_type:
            qs = qs.filter(content_type__model=object_type.lower())

        object_id = params.get('object_id')
        if object_id:
            qs = qs.filter(object_id=object_id)

        date_from = params.get('date_from')
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)

        date_to = params.get('date_to')
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        search = params.get('search')
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(reason__icontains=search) |
                Q(actor__email__icontains=search)
            )

        return qs

    @extend_schema(
        parameters=[
            OpenApiParameter('action', OpenApiTypes.STR, description='Filter by action code (e.g. review.submitted)'),
            OpenApiParameter('actor', OpenApiTypes.UUID, description='Filter by actor user ID'),
            OpenApiParameter('object_type', OpenApiTypes.STR, description='Filter by model name (e.g. submission, review)'),
            OpenApiParameter('object_id', OpenApiTypes.STR, description='Filter by object UUID'),
            OpenApiParameter('date_from', OpenApiTypes.DATE, description='Start date (inclusive, YYYY-MM-DD)'),
            OpenApiParameter('date_to', OpenApiTypes.DATE, description='End date (inclusive, YYYY-MM-DD)'),
            OpenApiParameter('search', OpenApiTypes.STR, description='Free-text search in reason and actor email'),
        ],
    )
    def list(self, request, *args, **kwargs):
        user = request.user
        if not (user.is_superuser or user.is_admin or user.is_organiser):
            return Response(
                {'detail': 'Only admins and organisers can access audit logs.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        user = request.user
        if not (user.is_superuser or user.is_admin or user.is_organiser):
            return Response(
                {'detail': 'Only admins and organisers can access audit logs.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().retrieve(request, *args, **kwargs)
