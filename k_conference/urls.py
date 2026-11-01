"""
K-Conference URL Configuration
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from apps.core.views import health, health_db

urlpatterns = [
    # Admin

    path('', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),

    path('admin/', admin.site.urls),

    # Health checks
    path('api/health/', health, name='health'),
    path('api/health/db/', health_db, name='health-db'),

    # API Schema (Swagger/ReDoc)
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc-ui'),

    # API v1
    path('api/v1/auth/', include('apps.accounts.urls.auth')),
    path('api/v1/accounts/', include('apps.accounts.urls.users')),
    path('api/v1/conferences/', include('apps.conferences.urls')),
    path('api/v1/submissions/', include('apps.submissions.urls')),
    path('api/v1/reviews/', include('apps.reviews.urls')),
    path('api/v1/scheduling/', include('apps.scheduling.urls')),
    path('api/v1/registrations/', include('apps.registrations.urls')),
    path('api/v1/communications/', include('apps.communications.urls')),
    path('api/v1/analytics/', include('apps.analytics.urls')),
    path('api/v1/audit/', include('apps.audit.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
