"""
App configuration for Conferences
"""

from django.apps import AppConfig


class ConferencesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.conferences'
    verbose_name = 'Conference Management'

    def ready(self):
        # Import signals to register them
        import apps.conferences.signals
