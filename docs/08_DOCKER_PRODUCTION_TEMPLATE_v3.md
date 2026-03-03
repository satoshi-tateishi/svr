# 08_DOCKER_PRODUCTION_TEMPLATE_v3.md

## 公演手配管理システム Docker本番構成（Ubuntu 24.04 & MySQL 8 統合版）

* * *

# 1. アーキテクチャ概要（v3）

本番環境は **Ubuntu 24.04 LTS** 上の Docker 構成を前提とする。

Plaintext

```
[Internet]
     ↓ HTTPS (443)
[Apache 2.4 (Host OS: Ubuntu 24.04)]
     ↓ Reverse Proxy (Unix Socket or localhost:8000)
[Gunicorn (Docker: Python 3.12-slim)]
     ↓
[Django 5.0+ (Docker)] 
     ↓
[MySQL 8.4 LTS (Docker)] ← JSON型・窓関数（乖離分析用）をフル活用
     ↓
[Redis 7 (Docker)] ← セッション・Celery Broker
```

* * *

# 2. Dockerfile（最適化版）

`mysqlclient` のビルドに必要な依存関係を整理し、軽量かつ堅牢な構成に変更。

Dockerfile

```
FROM python:3.12-slim

# OSレベルのセキュリティアップデートと依存パッケージ
RUN apt-get update && apt-get install -y 
    build-essential 
    pkg-config 
    default-libmysqlclient-dev 
    curl 
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 依存関係のインストール（キャッシュ利用）
COPY requirements.txt .
RUN pip install --upgrade pip && 
    pip install --no-cache-dir -r requirements.txt

# ソースコードとエントリポイント
COPY src/ /app/
COPY docker/*.sh /
RUN chmod +x /*.sh

ENTRYPOINT ["/entrypoint.sh"]
```

* * *

# 3. docker-compose.yml（MySQL 8.4 最適化）

MySQL 8.4 (LTS) を採用し、スナップショット（JSON）や大量の監査ログ検索に耐えるメモリ設定を追加。

YAML

```
version: "3.9"

services:
  db:
    image: mysql:8.4
    container_name: app_mysql
    restart: always
    # スナップショット検索と監査ログのIndex効率を上げるためのチューニング
    command: >
      --innodb-buffer-pool-size=1G
      --innodb-log-file-size=256M
      --character-set-server=utf8mb4
      --collation-server=utf8mb4_unicode_ci
    environment:
      MYSQL_DATABASE: ${MYSQL_DATABASE}
      MYSQL_USER: ${MYSQL_USER}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD}
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
    volumes:
      - mysql_data:/var/lib/mysql

  redis:
    image: redis:7-alpine
    container_name: app_redis
    restart: always

  web:
    build: .
    container_name: app_django
    restart: always
    env_file: .env
    depends_on:
      - db
      - redis
    ports:
      - "127.0.0.1:8000:8000" # ホストのApacheからのみ受け付ける

  celery:
    build: .
    container_name: app_celery
    restart: always
    command: ["/celery-entrypoint.sh"]
    env_file: .env
    depends_on:
      - db
      - redis

volumes:
  mysql_data:
```

* * *

# 4. Gunicorn設定（同時30人 + スナップショット処理）

`entrypoint.sh` 内の起動コマンドを、書き込み負荷（Lock処理）に強い設定に調整。

Bash

```
#!/bin/bash
# entrypoint.sh

python manage.py migrate --noinput
python manage.py collectstatic --noinput

# 30人同時利用 + 複雑なLockトランザクションを考慮
# 120秒のタイムアウトは、外部SaaS APIの遅延によるタイムアウトを防ぐため。
exec gunicorn config.wsgi:application 
    --bind 0.0.0.0:8000 
    --workers 5 
    --worker-class gthread 
    --threads 4 
    --timeout 120 
    --max-requests 2000 
    --access-logfile -
```

* * *

# 5. Apache (Ubuntu 24.04 Host) 設定

LINE WORKS SSO (OAuth2) 等のヘッダー保持と、リバースプロキシ設定。

Apache

```
<VirtualHost *:443>
    ServerName your-app.example.com

    SSLEngine on
    # SSL証明書の設定 (Certbot等)

    ProxyPreserveHost On
    ProxyPass / http://127.0.0.1:8000/
    ProxyPassReverse / http://127.0.0.1:8000/

    # セキュリティヘッダー（重要）
    Header always set X-Content-Type-Options "nosniff"
    Header always set X-Frame-Options "SAMEORIGIN"
    
    # スナップショット等の大容量JSONレスポンスを考慮した圧縮設定
    AddOutputFilterByType DEFLATE application/json
</VirtualHost>
```

* * *

# 6. バックアップと監査ログの維持

「過去を書き換えない」原則を守るためのバックアップ戦略。

-   **MySQL Dump**: スナップショット（JSONフィールド）を壊さないよう、`--hex-blob` オプションの使用を推奨。
-   **監査ログのローテーション**: `AuditLog` が50万件を超えたあたりからパフォーマンスに影響するため、`created_at` へのインデックスは必須。

* * *

# 7. アップデートの要点（v2からの変更点）

1.  **MySQL 8.4採用**: 最新のLTS版への固定。
2.  **メモリ割り当て増**: スナップショット生成と複雑な乖離分析（JOIN多用）に備え、DBのバッファプールを 1G に引き上げ。
3.  **GunicornのThread利用**: 同時接続時のレスポンス性能を向上。
4.  **Apacheの圧縮設定**: スナップショットデータの転送効率向上。
5.  **Ubuntu 24.04対応**: パッケージリストの最適化。



