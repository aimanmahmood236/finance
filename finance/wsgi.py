"""
WSGI config for library project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

import sys

# Add your project directory to the sys.path
path = os.path.expanduser('~/yourusername.pythonanywhere.com')
if path not in sys.path:
    sys.path.insert(0, path)

    
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'library.settings')

application = get_wsgi_application()
