"""Entry point for gunicorn: `gunicorn sensor_dashboard.wsgi:app`."""

from . import create_app

app = create_app()
