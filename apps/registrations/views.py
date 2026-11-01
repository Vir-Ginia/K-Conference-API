"""ViewSets for the Registrations app."""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BaseRenderer


class PassthroughRenderer(BaseRenderer):
    media_type = 'text/csv'
    format = 'csv'

    def render(self, data, *_, **__):
        return data
from django.shortcuts import get_object_or_404
import csv
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes

from apps.registrations.models import Registration
from apps.registrations.services import RegistrationService
from apps.registrations.serializers import (
    RegistrationListSerializer, RegistrationDetailSerializer,
    RegistrationCreateSerializer, RegistrationRejectSerializer,
    QRCheckInSerializer, QRSerializer, BulkStatusUpdateSerializer,
)


class RegistrationViewSet(viewsets.GenericViewSet):
    """
    Conference registration management.

    list        GET  /registrations/?conference=
    retrieve    GET  /registrations/{id}/
    create      POST /registrations/
    cancel      POST /registrations/{id}/cancel/
    approve     POST /registrations/{id}/approve/    (organiser)
    reject      POST /registrations/{id}/reject/     (organiser)
    check_in    POST /registrations/{id}/check-in/   (organiser)
    qr_check_in POST /registrations/qr-check-in/     (organiser)
    export      GET  /registrations/export/?conference=  (organiser)
    """
    queryset = Registration.objects.all()
    serializer_class = RegistrationDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Registration.objects.select_related(
            'conference', 'participant', 'reviewed_by'
        )
        if user.is_admin or user.is_superuser:
            pass
        elif user.is_organiser:
            qs = qs.filter(conference__organiser=user)
        else:
            qs = qs.filter(participant=user)

        conference = self.request.query_params.get('conference')
        if conference:
            qs = qs.filter(conference=conference)

        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        return qs

    @extend_schema(
        parameters=[
            OpenApiParameter('conference', OpenApiTypes.UUID, description='Filter by conference ID'),
            OpenApiParameter('status', OpenApiTypes.STR, description='Filter by status (pending, approved, rejected, cancelled)'),
        ],
        responses=RegistrationListSerializer(many=True),
    )
    def list(self, request):
        qs = self.get_queryset()
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(RegistrationListSerializer(page, many=True).data)
        return Response(RegistrationListSerializer(qs, many=True).data)

    @extend_schema(responses=RegistrationDetailSerializer)
    def retrieve(self, request, pk=None):
        reg = get_object_or_404(self.get_queryset(), pk=pk)
        return Response(RegistrationDetailSerializer(reg).data)

    @extend_schema(request=RegistrationCreateSerializer, responses={201: RegistrationDetailSerializer})
    def create(self, request):
        serializer = RegistrationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from apps.conferences.models import Conference
        conference = get_object_or_404(Conference, pk=serializer.validated_data['conference'].pk)
        try:
            registration = RegistrationService.register(
                user=request.user,
                conference=conference,
                ticket_type=serializer.validated_data.get('ticket_type', 'standard'),
                notes=serializer.validated_data.get('notes', ''),
            )
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            RegistrationDetailSerializer(registration).data,
            status=status.HTTP_201_CREATED
        )

    @extend_schema(responses=QRSerializer)
    @action(detail=True, methods=['get'], url_path='qr')
    def qr(self, request, pk=None):
        """Return the QR token for a registration. Only accessible by the participant or organiser."""
        reg = get_object_or_404(Registration, pk=pk)
        user = request.user
        if user != reg.participant and not (user.is_organiser or user.is_admin):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You do not have access to this QR code.")
        if reg.status not in ('approved', 'checked_in'):
            return Response(
                {'detail': 'QR code is only available for approved registrations.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(QRSerializer(reg).data)

    @extend_schema(request=None, responses=RegistrationDetailSerializer)
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Participant cancels their own registration."""
        reg = get_object_or_404(Registration, pk=pk, participant=request.user)
        try:
            reg = RegistrationService.cancel(request.user, reg)
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(RegistrationDetailSerializer(reg).data)

    @extend_schema(request=None, responses=RegistrationDetailSerializer)
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Organiser approves a registration."""
        self._require_organiser()
        reg = get_object_or_404(self._organiser_qs(), pk=pk)
        try:
            reg = RegistrationService.approve(request.user, reg)
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(RegistrationDetailSerializer(reg).data)

    @extend_schema(request=RegistrationRejectSerializer, responses=RegistrationDetailSerializer)
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Organiser rejects a registration."""
        self._require_organiser()
        reg = get_object_or_404(self._organiser_qs(), pk=pk)
        serializer = RegistrationRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            reg = RegistrationService.reject(
                request.user, reg, reason=serializer.validated_data.get('reason', '')
            )
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(RegistrationDetailSerializer(reg).data)

    @extend_schema(request=None, responses=RegistrationDetailSerializer)
    @action(detail=True, methods=['post'], url_path='check-in')
    def check_in(self, request, pk=None):
        """Manual check-in by organiser."""
        self._require_organiser()
        reg = get_object_or_404(self._organiser_qs(), pk=pk)
        try:
            reg = RegistrationService.check_in(request.user, reg)
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(RegistrationDetailSerializer(reg).data)

    @extend_schema(
        request=BulkStatusUpdateSerializer,
        responses={(200, 'application/json'): {
            'type': 'object',
            'properties': {
                'updated_count': {'type': 'integer'},
                'failed_count': {'type': 'integer'},
                'updated': {'type': 'array', 'items': {'type': 'string'}},
                'failed': {'type': 'array', 'items': {'type': 'object'}},
            }
        }},
    )
    @action(detail=False, methods=['post'], url_path='bulk-update')
    def bulk_update(self, request):
        """Bulk approve or reject registrations. Organiser/admin only."""
        self._require_organiser()
        serializer = BulkStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = RegistrationService.bulk_update_status(
            organiser=request.user,
            registration_ids=serializer.validated_data['ids'],
            target_status=serializer.validated_data['status'],
            reason=serializer.validated_data.get('reason', ''),
        )
        return Response(result)

    @extend_schema(request=QRCheckInSerializer, responses=RegistrationDetailSerializer)
    @action(detail=False, methods=['post'], url_path='qr-check-in')
    def qr_check_in(self, request):
        """QR code-based check-in."""
        self._require_organiser()
        serializer = QRCheckInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            reg = RegistrationService.check_in_by_qr(
                request.user, serializer.validated_data['qr_code']
            )
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(RegistrationDetailSerializer(reg).data)

    @extend_schema(
        parameters=[OpenApiParameter('conference', OpenApiTypes.UUID, required=True, description='Conference ID')],
        responses={(200, 'text/csv'): OpenApiTypes.BINARY},
    )
    @action(detail=False, methods=['get'], renderer_classes=[PassthroughRenderer])
    def export(self, request):
        """Export attendance list as CSV. Organiser only."""
        self._require_organiser()
        conference_id = request.query_params.get('conference')
        if not conference_id:
            return Response({'detail': 'conference param required.'}, status=status.HTTP_400_BAD_REQUEST)

        qs = Registration.objects.filter(
            conference=conference_id,
            conference__organiser=request.user,
        ).select_related('participant', 'conference').order_by('status', 'registered_at')

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="registrations_{conference_id}.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'ID', 'Name', 'Email', 'Ticket Type', 'Status',
            'Checked In', 'Checked In At', 'Registered At', 'Notes'
        ])
        for reg in qs:
            writer.writerow([
                str(reg.id),
                reg.participant.get_full_name() or reg.participant.email,
                reg.participant.email,
                reg.get_ticket_type_display(),
                reg.get_status_display(),
                reg.checked_in,
                reg.checked_in_at.isoformat() if reg.checked_in_at else '',
                reg.registered_at.isoformat(),
                reg.notes,
            ])
        return response

    def _require_organiser(self):
        if not (self.request.user.is_organiser or self.request.user.is_admin):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only organisers can perform this action.")

    def _organiser_qs(self):
        user = self.request.user
        qs = Registration.objects.select_related('conference', 'participant')
        if not (user.is_admin or user.is_superuser):
            qs = qs.filter(conference__organiser=user)
        return qs
