"""Django admin for the Analytics app."""
from django.contrib import admin
from apps.analytics.models import AnalyticsReport


@admin.register(AnalyticsReport)
class AnalyticsReportAdmin(admin.ModelAdmin):
    list_display = ('conference', 'report_type', 'generated_by', 'generated_at')
    list_filter = ('report_type', 'conference')
    search_fields = ('conference__title', 'generated_by__email')
    readonly_fields = ('generated_at', 'data', 'generated_by', 'conference', 'report_type')
    ordering = ('-generated_at',)

    def has_add_permission(self, request):
        return False  # Reports are generated via API only

    def has_change_permission(self, request, obj=None):
        return False  # Read-only
