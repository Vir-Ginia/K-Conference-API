"""
WSGI config for k_conference project.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'k_conference.settings')

application = get_wsgi_application()
