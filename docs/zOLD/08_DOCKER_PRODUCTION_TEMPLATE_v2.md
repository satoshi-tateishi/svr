# DOCKER_PRODUCTION_TEMPLATE_v2.md

## 公演手配管理システム Docker本番構成テンプレート（スナップショット・監査ログ強化対応）

（ApacheはホストOSで実行）

* * *

# 1. アーキテクチャ概要（v2）

Plain text

[Internet]  
     ↓  
[Apache (Host OS)]  
     ↓ Reverse Proxy (localhost:8000)  
[Gunicorn (Docker)]  
     ↓  
[Django App (Docker)]  
     ↓  
[MySQL 8 (Docker)]  
     ↓  
[Redis (Docker)]  
     ↓  
[Celery Worker (Docker)]

※ Celeryは将来請求生成/API非同期化用（推奨）

* * *

# 2. ディレクトリ構成

Bash

project-root/  
 ├── docker/  
 │    ├── Dockerfile  
 │    ├── entrypoint.sh  
 │    ├── celery-entrypoint.sh  
 │  
 ├── docker-compose.yml  
 ├── .env  
 ├── requirements.txt  
 └── src/  
      └── manage.py

* * *

# 3. Dockerfile（最適化版）

dockerfile

FROM python:3.12-slim  
  
ENV PYTHONDONTWRITEBYTECODE=1  
ENV PYTHONUNBUFFERED=1  
  
RUN apt-get update && apt-get install -y   
    build-essential   
    default-libmysqlclient-dev   
    && rm -rf /var/lib/apt/lists/*  
  
WORKDIR /app  
  
COPY requirements.txt .  
RUN pip install --upgrade pip  
RUN pip install --no-cache-dir -r requirements.txt  
  
COPY src/ /app/  
COPY docker/entrypoint.sh /entrypoint.sh  
COPY docker/celery-entrypoint.sh /celery-entrypoint.sh  
  
RUN chmod +x /entrypoint.sh  
RUN chmod +x /celery-entrypoint.sh  
  
ENTRYPOINT ["/entrypoint.sh"]

* * *

# 4. entrypoint.sh（Gunicorn最適化）

Bash

#!/bin/bash  
  
python manage.py migrate --noinput  
python manage.py collectstatic --noinput  
  
exec gunicorn config.wsgi:application   
    --bind 0.0.0.0:8000   
    --workers 4   
    --worker-class sync   
    --max-requests 1000   
    --max-requests-jitter 100   
    --timeout 120   
    --graceful-timeout 30

※ workers=4（30人規模 + スナップショット処理考慮）

* * *

# 5. Celery Worker（追加）

## celery-entrypoint.sh

Bash

#!/bin/bash  
  
exec celery -A config worker   
    --loglevel=info   
    --concurrency=2

* * *

# 6. docker-compose.yml（v2）

YAML

version: "3.9"  
  
services:  
  
  db:  
    image: mysql:8.0  
    container_name: app_mysql  
    restart: always  
    command: >  
      --default-authentication-plugin=mysql_native_password  
      --innodb-buffer-pool-size=512M  
    environment:  
      MYSQL_DATABASE: ${MYSQL_DATABASE}  
      MYSQL_USER: ${MYSQL_USER}  
      MYSQL_PASSWORD: ${MYSQL_PASSWORD}  
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}  
    volumes:  
      - mysql_data:/var/lib/mysql  
  
  redis:  
    image: redis:7  
    container_name: app_redis  
    restart: always  
  
  web:  
    build:  
      context: .  
      dockerfile: docker/Dockerfile  
    container_name: app_django  
    restart: always  
    env_file:  
      - .env  
    depends_on:  
      - db  
      - redis  
    ports:  
      - "8000:8000"  
  
  celery:  
    build:  
      context: .  
      dockerfile: docker/Dockerfile  
    container_name: app_celery  
    restart: always  
    command: ["/celery-entrypoint.sh"]  
    env_file:  
      - .env  
    depends_on:  
      - db  
      - redis  
  
volumes:  
  mysql_data:

* * *

# 7. .env（v2追加項目）

Bash

DEBUG=False  
SECRET_KEY=change-me-strong-key  
  
ALLOWED_HOSTS=your-domain.com  
  
MYSQL_DATABASE=performance_db  
MYSQL_USER=app_user  
MYSQL_PASSWORD=secure_password  
MYSQL_ROOT_PASSWORD=root_secure_password  
MYSQL_HOST=db  
MYSQL_PORT=3306  
  
REDIS_HOST=redis  
REDIS_PORT=6379  
  
CELERY_BROKER_URL=redis://redis:6379/0  
CELERY_RESULT_BACKEND=redis://redis:6379/1

* * *

# 8. Django settings.py 追加設定

Python

import os  
  
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS").split(",")  
  
DATABASES = {  
    "default": {  
        "ENGINE": "django.db.backends.mysql",  
        "NAME": os.getenv("MYSQL_DATABASE"),  
        "USER": os.getenv("MYSQL_USER"),  
        "PASSWORD": os.getenv("MYSQL_PASSWORD"),  
        "HOST": os.getenv("MYSQL_HOST"),  
        "PORT": os.getenv("MYSQL_PORT"),  
        "OPTIONS": {  
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'"  
        }  
    }  
}  
  
STATIC_ROOT = "/app/staticfiles"  
  
# Celery  
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL")  
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND")

* * *

# 9. Apache（ホスト側）

変更なしだがセキュリティ強化推奨：

apache

Header always set X-Content-Type-Options "nosniff"  
Header always set X-Frame-Options "DENY"  
Header always set X-XSS-Protection "1; mode=block"

* * *

# 10. 監査ログ肥大化対策（重要）

### MySQL index追加（必須）

SQL

CREATE INDEX idx_audit_created_at ON audit_log(created_at);  
CREATE INDEX idx_audit_event_type ON audit_log(event_type);  
CREATE INDEX idx_audit_related_id ON audit_log(related_object_id);

### 5年以上はアーカイブ推奨

* * *

# 11. バックアップ戦略（強化版）

## 毎日自動バックアップ推奨

Bash

docker exec app_mysql   
mysqldump -u root -p${MYSQL_ROOT_PASSWORD} performance_db   
| gzip > backup_$(date +%F).sql.gz

### 保持：

-   日次7日
-   月次12ヶ月
-   年次5年（監査ログ対応）

* * *

# 12. セキュリティ強化（v2）

必須：

-   DEBUG=False
-   SECRET_KEYは32文字以上
-   MySQL外部公開禁止
-   Redis外部公開禁止
-   ufwで80/443のみ開放
-   fail2ban推奨
-   Docker rootless推奨

* * *

# 13. スナップショット設計考慮チューニング

-   InnoDB有効
-   JSONフィールド利用（MySQL 8必須）
-   select_for_update徹底
-   トランザクション分離レベル確認（REPEATABLE READ）

* * *

# 14. 同時30人 + スナップショット対応

推奨：

-   Gunicorn workers=4
-   Celery concurrency=2
-   MySQL buffer_pool 512MB以上
-   Redis maxmemory設定

* * *

# 15. 本番デプロイフロー（安全版）

1.  Git pull
2.  docker compose build
3.  docker compose up -d
4.  docker compose exec web python manage.py migrate
5.  ログ確認
6.  Snapshot動作確認
7.  API送信テスト

* * *

# v2の完成度

-   単価スナップショット対応
-   監査ログ肥大化耐性
-   非同期処理拡張可能
-   改ざん耐性前提設計
-   小規模企業に最適化済

