"""
svr WSGI 設定

Gunicorn / Apache mod_wsgi から呼び出されるエントリポイント。
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()
