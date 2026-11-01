"""ViewSets for the Analytics app. All endpoints are read-only and organiser-only."""
import csv
import json
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BaseRenderer
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes


class PassthroughRenderer(BaseRenderer):
    """Renderer that passes through a raw HttpResponse without modification."""
    media_type = 'text/csv'
    format = 'csv'

    def render(self, data, *_, **__):
        return data

from apps.analytics.models import AnalyticsReport
from apps.analytics.services import AnalyticsService
from apps.conferences.models import Conference

_CONF_PARAM = [OpenApiParameter('conference', OpenApiTypes.UUID, required=True, description='Conference ID')]


class AnalyticsViewSet(viewsets.GenericViewSet):
    """
    Read-only analytics and reporting for conference organisers.

    overview        GET /analytics/overview/?conference=
    submissions     GET /analytics/submissions/?conference=
    reviews         GET /analytics/reviews/?conference=
    registrations   GET /analytics/registrations/?conference=
    attendance      GET /analytics/attendance/?conference=
    export          GET /analytics/export/?conference=&type=  (CSV download)
    saved_reports   GET /analytics/saved/?conference=
    """
    queryset = AnalyticsReport.objects.all()
    permission_classes = [IsAuthenticated]

    def _get_conference(self):
        conference_id = self.request.query_params.get('conference')
        if not conference_id:
            return None, Response(
                {'detail': 'conference query param is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        user = self.request.user
        qs = Conference.objects.all()
        if not (user.is_admin or user.is_superuser):
            if not (user.is_organiser):
                return None, Response(
                    {'detail': 'Only organisers can access analytics.'},
                    status=status.HTTP_403_FORBIDDEN
                )
            qs = qs.filter(organiser=user)
        conference = get_object_or_404(qs, pk=conference_id)
        return conference, None

    @extend_schema(parameters=_CONF_PARAM, responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=['get'])
    def overview(self, request):
        """High-level dashboard — submissions, reviews, registrations, sessions."""
        conference, err = self._get_conference()
        if err:
            return err
        data = AnalyticsService.overview(conference)
        return Response(data)

    @extend_schema(parameters=_CONF_PARAM, responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=['get'])
    def submissions(self, request):
        """Submission counts, acceptance rate, per-track breakdown, keywords, demographics."""
        conference, err = self._get_conference()
        if err:
            return err
        data = AnalyticsService.submission_stats(conference)
        return Response(data)

    @extend_schema(parameters=_CONF_PARAM, responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=['get'])
    def reviews(self, request):
        """Review progress, completion rates, score distributions, recommendation breakdown."""
        conference, err = self._get_conference()
        if err:
            return err
        data = AnalyticsService.review_stats(conference)
        return Response(data)

    @extend_schema(parameters=_CONF_PARAM, responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=['get'])
    def registrations(self, request):
        """Registration counts by status/ticket type, capacity, registrations over time."""
        conference, err = self._get_conference()
        if err:
            return err
        data = AnalyticsService.registration_stats(conference)
        return Response(data)

    @extend_schema(parameters=_CONF_PARAM, responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=['get'])
    def attendance(self, request):
        """Check-in counts, check-ins by hour, session summary."""
        conference, err = self._get_conference()
        if err:
            return err
        data = AnalyticsService.attendance_stats(conference)
        return Response(data)

    @extend_schema(
        parameters=_CONF_PARAM + [
            OpenApiParameter('type', OpenApiTypes.STR, description='Report type: overview, submissions, reviews, registrations, attendance'),
        ],
        responses={(200, 'text/csv'): OpenApiTypes.BINARY},
    )
    @action(detail=False, methods=['get'], renderer_classes=[PassthroughRenderer])
    def export(self, request):
        """
        Export a report as CSV.
        ?conference=<id>&type=<submissions|reviews|registrations|attendance|overview>
        """
        conference, err = self._get_conference()
        if err:
            return err

        report_type = request.query_params.get('type', 'overview')
        service_map = {
            'overview': AnalyticsService.overview,
            'submissions': AnalyticsService.submission_stats,
            'reviews': AnalyticsService.review_stats,
            'registrations': AnalyticsService.registration_stats,
            'attendance': AnalyticsService.attendance_stats,
        }

        if report_type not in service_map:
            return Response(
                {'detail': f'Invalid type. Choose from: {", ".join(service_map.keys())}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        data = service_map[report_type](conference)

        # Save snapshot
        AnalyticsReport.objects.create(
            conference=conference,
            report_type=report_type,
            generated_by=request.user,
            data=data,
        )

        # Flatten nested data to CSV rows
        http_response = HttpResponse(content_type='text/csv')
        http_response['Content-Disposition'] = (
            f'attachment; filename="{conference.short_name}_{report_type}_report.csv"'
        )
        writer = csv.writer(http_response)

        def flatten(d, prefix=''):
            """Recursively flatten dict to (key, value) rows."""
            rows = []
            for k, v in d.items():
                full_key = f"{prefix}.{k}" if prefix else k
                if isinstance(v, dict):
                    rows.extend(flatten(v, full_key))
                elif isinstance(v, list):
                    rows.append((full_key, json.dumps(v)))
                else:
                    rows.append((full_key, v))
            return rows

        writer.writerow(['Metric', 'Value'])
        for key, value in flatten(data):
            writer.writerow([key, value])

        return http_response

    @extend_schema(parameters=_CONF_PARAM, responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=['get'], url_path='saved')
    def saved_reports(self, request):
        """List previously generated/saved report snapshots for a conference."""
        conference, err = self._get_conference()
        if err:
            return err

        reports = AnalyticsReport.objects.filter(conference=conference).order_by('-generated_at')
        return Response([
            {
                'id': str(r.id),
                'report_type': r.report_type,
                'report_type_display': r.get_report_type_display(),
                'generated_by': r.generated_by.email if r.generated_by else None,
                'generated_at': r.generated_at.isoformat(),
            }
            for r in reports
        ])

    @extend_schema(
        parameters=_CONF_PARAM + [
            OpenApiParameter('report_id', OpenApiTypes.UUID, OpenApiParameter.PATH, description='Report ID'),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=['get'], url_path=r'saved/(?P<report_id>[^/.]+)')
    def saved_report_detail(self, request, report_id=None):
        """Retrieve the full data of a saved report snapshot."""
        conference, err = self._get_conference()
        if err:
            return err
        report = get_object_or_404(AnalyticsReport, pk=report_id, conference=conference)
        return Response({
            'id': str(report.id),
            'report_type': report.report_type,
            'generated_by': report.generated_by.email if report.generated_by else None,
            'generated_at': report.generated_at.isoformat(),
            'data': report.data,
        })
