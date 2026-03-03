"""
テスト専用設定

インメモリ SQLite・LocMemCache を使用することで、
MySQL / Redis への接続なしにテストを実行できる。

pytest.ini_options の DJANGO_SETTINGS_MODULE をこのモジュールに向けること。
"""

# 環境変数のセットは settings.py のインポートより前に行う必要があるため、
# os.environ で直接設定する（pytest-django はプラグイン初期化時に Django をセットアップするため）
import os

os.environ.setdefault('SECRET_KEY', 'test-secret-key-for-pytest-only')
os.environ.setdefault('DEBUG', 'True')
os.environ.setdefault('DATABASE_URL', 'sqlite://:memory:')

from config.settings import *  # noqa: E402, F403, F401

# テスト用 DB: インメモリ SQLite（MySQL 接続不要）
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# テスト用キャッシュ: LocMemCache（Redis 接続不要）
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

# セッションもメモリ上で処理（Redis 不要）
SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# パスワードハッシュを高速化（テスト用）
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
