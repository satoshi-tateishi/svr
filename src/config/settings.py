"""
svr Django 設定ファイル

このファイルは django-admin startproject で生成したものをベースに、
shin•on Portal JWT 連携設定を追加したテンプレートです。
"""

import os
import sys
from pathlib import Path

import environ

# BASE_DIR: このファイルの2階層上 = /app（コンテナ内のプロジェクトルート）
BASE_DIR = Path(__file__).resolve().parent.parent

TESTING = 'test' in sys.argv

env = environ.Env(DEBUG=(bool, False))
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

SECRET_KEY = env('SECRET_KEY', default='django-insecure-change-me')
DEBUG = env('DEBUG')
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['*'])

# Apache リバースプロキシ背後での HTTPS 認識
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

CSRF_TRUSTED_ORIGINS = env.list(
    'CSRF_TRUSTED_ORIGINS', default=['http://localhost:8085', 'http://127.0.0.1:8085']
)

# ============================================================
# Application definition
# ============================================================

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Local apps
    'apps.accounts',
    'apps.performances',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    # shin•on Portal の portal_jwt クッキーを検証して Django セッションに紐付ける
    # AuthenticationMiddleware の直後に配置することで、未認証時のみ JWT 認証を試みる
    'apps.accounts.middleware.PortalJWTMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.accounts.context_processors.portal_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# ============================================================
# Database（MySQL 8.4 LTS）
# ============================================================

DATABASES = {'default': env.db('DATABASE_URL', default='mysql://user:password@db:3306/svr_db')}

# ============================================================
# Cache & Session（Redis）
# ============================================================

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': env('REDIS_URL', default='redis://redis:6379/0'),
        'OPTIONS': {'CLIENT_CLASS': 'django_redis.client.DefaultClient'},
    }
}

SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'

# ============================================================
# Authentication
# ============================================================

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# login_required デコレータのリダイレクト先（PortalJWTMiddleware 経由でポータルへ）
LOGIN_URL = 'accounts:login'

# ============================================================
# Internationalization
# ============================================================

LANGUAGE_CODE = 'ja'
TIME_ZONE = 'Asia/Tokyo'
USE_I18N = True
USE_TZ = True

# ============================================================
# Static files
# ============================================================

STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ============================================================
# shin•on Portal JWT 連携設定
# PortalJWTMiddleware が portal_jwt クッキーを検証するために使用する
# ============================================================

# JWKS エンドポイント（Docker 内からは http://portal-app:8000/api/jwks/ でアクセス）
PORTAL_JWKS_URL = env('PORTAL_JWKS_URL', default='http://portal-app:8000/api/jwks/')

# JWT の iss クレームと照合する発行者（ポータルの PORTAL_JWT_ISSUER と一致させること）
PORTAL_JWT_ISSUER = env('PORTAL_JWT_ISSUER', default='https://portal.shin-on1981.com')

# JWT の aud クレームと照合する対象（ポータルの PORTAL_JWT_AUDIENCE と一致させること）
PORTAL_JWT_AUDIENCE = env('PORTAL_JWT_AUDIENCE', default='shin-on-apps')

# 未認証時のリダイレクト先（開発: http://localhost/login/ / 本番: https://portal.shin-on1981.com/login/）
PORTAL_LOGIN_URL = env('PORTAL_LOGIN_URL', default='http://localhost/login/')
# ポータルトップURL（PORTAL_LOGIN_URL からパスを除いたベースURL）
PORTAL_URL = '/'.join(PORTAL_LOGIN_URL.split('/')[:3]) + '/'

# ============================================================
# セキュリティ設定（本番）
# ============================================================

SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_HSTS_SECONDS = 0 if DEBUG else 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG

# ============================================================
# Celery 設定（非同期タスク: freee/board 連携予定）
# ============================================================

CELERY_BROKER_URL = env('REDIS_URL', default='redis://redis:6379/0')
CELERY_RESULT_BACKEND = env('REDIS_URL', default='redis://redis:6379/0')
CELERY_TIMEZONE = 'Asia/Tokyo'

# プロキシ経由でのリダイレクト先ホスト/ポートの維持設定
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
