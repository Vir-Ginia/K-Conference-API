"""App configuration for Scheduling"""
from django.apps import AppConfig

class SchedulingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.scheduling'
    verbose_name = 'Conference Scheduling'

    def ready(self):
        pass  # No signals needed — notifications triggered from service layer
