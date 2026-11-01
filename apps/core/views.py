"""Health check endpoints."""
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status


@api_view(['GET'])
@permission_classes([AllowAny])
def health(request):
    """Basic liveness check — returns 200 if the app is running."""
    return Response({'status': 'ok', 'timestamp': timezone.now().isoformat()})


@api_view(['GET'])
@permission_classes([AllowAny])
def health_db(request):
    """Database connectivity check — queries the DB and reports status."""
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        return Response({'status': 'ok', 'database': 'connected', 'timestamp': timezone.now().isoformat()})
    except Exception as e:
        return Response(
            {'status': 'error', 'database': 'unavailable', 'detail': str(e)},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
