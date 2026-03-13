# Docker / 本番構成メモ

## 1. 現行の開発用 Compose 構成

`docker-compose.yml` の実装は以下です。

- `db`: `mysql:8.4`, コンテナ名 `svr_db`, ホストポート `3310`
- `redis`: `redis:7-alpine`, コンテナ名 `svr_redis`
- `web`: コンテナ名 `svr_web`, ホストポート `8085`

ネットワーク:

- `svr_network`
- `shin-on-internal`（外部ネットワーク、Portal 通信用）

## 2. `web` コンテナの現行起動方式

開発用は Gunicorn ではなく Django 開発サーバです。

```yaml
command: python manage.py runserver 0.0.0.0:8000
```

したがって、旧版ドキュメントにある本番 Gunicorn 設定はまだ適用されていません。

## 3. Dockerfile の現状

- ベースイメージ: `python:3.12-slim`
- MySQL クライアントビルド依存を導入
- WeasyPrint 依存を導入
- 日本語フォント `fonts-noto-cjk` を導入

## 4. Django 設定上の前提

- DB: `DATABASE_URL`
- Redis: `REDIS_URL`
- Portal JWT:
  - `PORTAL_JWKS_URL`
  - `PORTAL_JWT_ISSUER`
  - `PORTAL_JWT_AUDIENCE`
  - `PORTAL_LOGIN_URL`

## 5. 本番化でまだ必要なもの

- Gunicorn 起動設定
- 静的ファイル収集フロー
- Apache / リバースプロキシ実設定
- HTTPS 終端の確定
- ヘルスチェック運用

## 6. 注意

- 現行リポジトリには `manage.py` は `src/` 配下にあり、Compose の `web` は `/app` として `src` をマウントしている
- テストは Compose ではなく `docker run --rm ... svr_web python -m pytest ...` の運用を前提にしている
