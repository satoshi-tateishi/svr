# 12_PORTAL_INTEGRATION_GUIDE.md

## svr × shin•on Portal JWT 連携ガイド

このドキュメントは `svr`（演劇制作人員・配車・工程管理システム）と
`shin•on Portal` の JWT 認証連携について記録したものです。

---

## 1. 認証フロー全体像

```
[ユーザー]
  │
  ├─① 未認証で svr にアクセス（http://localhost:8085/）
  │
[svr]
  │  login_required → accounts:login → /auth/login/?next=/path/
  │
  ├─② ポータルログイン画面へリダイレクト
  │   http://localhost/login/?next=http://localhost:8085/path/
  │
[shin•on Portal]
  │  LINE WORKS SSO → OTP 検証
  │  set_otp_cookie() → portal_jwt クッキー発行 → next_url へリダイレクト
  │
[svr]
  │  PortalJWTMiddleware が portal_jwt を検証
  │  → ユーザー照合 or 自動作成 → Django セッション確立
  │
  └─③ svr のコンテンツを表示
```

---

## 2. 実装済みファイル一覧

| ファイル | 内容 |
|---------|------|
| `src/apps/accounts/middleware.py` | PortalJWTMiddleware（JWT 検証・ユーザー自動作成） |
| `src/apps/accounts/models.py` | UserProfile（portal_uuid・JWT 同期フィールド・SystemRole） |
| `src/apps/accounts/views.py` | login_view / logout_view |
| `src/apps/accounts/urls.py` | `/auth/login/`, `/auth/logout/` |
| `src/apps/accounts/admin.py` | Admin UI（JWT 同期フィールドは読み取り専用） |
| `src/config/settings.py` | Django 設定（PORTAL_JWKS_URL 等含む） |
| `docker-compose.yml` | shin-on-internal ネットワーク設定済み |
| `.env.sample` | 環境変数サンプル |

---

## 3. svr 固有の設定値

| 項目 | 値 |
|-----|---|
| コンテナ名 | `svr_web` |
| 開発ポート | `8085`（rf_finder が 8084 を使用中） |
| DB コンテナ名 | `svr_db` |
| DB 開発ポート | `3310`（rf_finder が 3309、portal が 3306 を使用中） |
| Docker ネットワーク | `svr_network`（内部）+ `shin-on-internal`（Portal 通信用） |

---

## 4. 初回セットアップ手順

### 4-1. Django プロジェクトのスキャフォールド

```bash
# 必要なら Django プロジェクトの骨格を生成
# ※ settings.py・urls.py・wsgi.py は src/config/ 以下に配置
cd /Users/satoshi/svr
docker compose run --rm web django-admin startproject config .
```

### 4-2. 必要なディレクトリとファイルを確認

```
src/
├── apps/
│   └── accounts/    ← 実装済み
├── config/
│   ├── __init__.py  ← 実装済み
│   ├── settings.py  ← 実装済み
│   ├── urls.py      ← 要作成（下記参照）
│   └── wsgi.py      ← 要作成（startproject で生成）
└── manage.py        ← 要作成（startproject で生成）
```

### 4-3. config/urls.py に accounts URL を追加

```python
# src/config/urls.py
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/', include('apps.accounts.urls')),
    # 業務アプリ（別フェーズ）
    # path('', include('apps.performances.urls')),
]
```

### 4-4. 環境変数を設定

```bash
cp .env.sample .env
# .env を編集して SECRET_KEY・DB パスワード等を設定
```

### 4-5. shin-on-internal ネットワークを作成（未作成の場合のみ）

```bash
# portal-app および rf_finder が既に作成済みなら不要
docker network create shin-on-internal

# portal-app コンテナをネットワークに接続（まだ接続されていない場合）
docker network connect shin-on-internal portal-app
```

### 4-6. shin-on_portal の PORTAL_ALLOWED_REDIRECT_HOSTS を確認

`/Users/satoshi/shin-on_portal/portal-app/.env` を開いて確認：

```env
# 既に ["localhost"] が設定されていれば追加不要
PORTAL_ALLOWED_REDIRECT_HOSTS=["localhost"]
```

`localhost` が含まれていない場合は追加してコンテナを再起動：

```bash
cd /Users/satoshi/shin-on_portal
docker compose restart portal-app
```

### 4-7. svr を起動してマイグレーション

```bash
cd /Users/satoshi/svr
docker compose up -d
docker compose exec web python manage.py makemigrations accounts
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

---

## 5. 動作確認チェックリスト

```
□ shin-on_portal のコンテナが起動しており、portal-app が shin-on-internal に接続済み
□ docker compose up -d でコンテナ起動
□ http://localhost:8085/ にアクセス
□   → http://localhost/login/?next=http://localhost:8085/ にリダイレクト
□ ポータルで SSO + OTP 認証完了
□   → svr（localhost:8085）に戻り Django セッションが確立
□ /admin/accounts/userprofile/ に UserProfile が自動作成されていることを確認
□ portal_uuid フィールドに portal の User.username（UUID v4）が格納されていることを確認
□ phone_number が JWT から同期されていることを確認
```

---

## 6. JWT ペイロード（portal が発行するクレーム）

```json
{
  "iss": "https://portal.shin-on1981.com",
  "sub": "<portal_uuid>",
  "aud": "shin-on-apps",
  "iat": 1234567890,
  "exp": 1234654290,
  "jti": "<uuid4>",
  "email": "user@shin-on1981.com",
  "name": "山田太郎",
  "given_name": "太郎",
  "family_name": "山田",
  "phonetic_given_name": "たろう",
  "phonetic_family_name": "やまだ",
  "phone_number": "09012345678",
  "is_active": true
}
```

**重要**: `sub` は `portal_uuid`（= Portal の `User.username`）。
不変の識別子として svr の `UserProfile.portal_uuid` に保存し、
公演の人員割当（`StaffAssignment.user`）の参照に使用する。

---

## 7. UserProfile のロール設計

svr では権限を「システムロール」と「公演内ロール」の2層で管理する。

### システムロール（`UserProfile.system_role`）

| ロール | 説明 | Django staff |
|--------|------|-------------|
| `admin` | 単価登録・Lock解除・監査ログ全閲覧 | is_staff=True, is_superuser=True |
| `editor` | Lock実行・フリーランス単価登録 | is_staff=False |
| `general` | 通常業務・自分の担当公演のみ | is_staff=False |
| `viewer` | 閲覧のみ | is_staff=False |

### 公演内ロール（`PerformanceMember.role`）※別フェーズ実装

| ロール | 説明 |
|--------|------|
| `planner` | 公演責任者（単価・原価閲覧可、Lock実行可） |
| `chief` | 現場責任者（単価・原価は**秘匿**） |
| `sub` | 補助スタッフ（限定的なアクセス） |

---

## 8. 重要なハマりポイント

### post_save シグナルとの干渉バグ

新規ユーザー作成後に `get_or_create` で UserProfile を取得すると、
`login()` が発火する `save_user_profile` シグナルで `portal_uuid=None` に上書きされる。

**正しい実装**（`user.profile` 経由でキャッシュを更新する）：

```python
# middleware.py の新規ユーザー作成部分
user = User.objects.create_user(username=portal_uuid, email=email, password=None)
profile = user.profile  # ← get_or_create ではなく user.profile でキャッシュ更新
profile.portal_uuid = portal_uuid
profile.save()
```

詳細: `/Users/satoshi/rf_finder/docs/01_APP_INTEGRATION_GUIDE.md`
「Django post_save シグナルとの干渉バグ」参照。

### OTP 完了後にポータルトップに飛んでしまう

**原因**: `_get_safe_redirect_url` が `next_url` を弾いている。

**確認方法**: `/Users/satoshi/shin-on_portal/portal-app/.env` の
`PORTAL_ALLOWED_REDIRECT_HOSTS` に `localhost` が含まれているか確認。

### `portal_jwt` クッキーが届くが認証されない

1. `PORTAL_JWT_ISSUER` / `PORTAL_JWT_AUDIENCE` がポータル設定と一致しているか確認
2. `PORTAL_JWKS_URL` が `portal-app` コンテナに疎通できるか確認
3. `docker compose logs web` でエラーログを確認

### DB 接続エラー（`Can't connect to server on 'db'`）

`docker-compose.yml` の `depends_on` に `condition: service_healthy` が
設定されているか確認（`healthcheck` も必須）。

---

## 9. 参照ドキュメント

| ドキュメント | 場所 |
|------------|------|
| 連携仕様・ハマりポイント正典 | `/Users/satoshi/rf_finder/docs/01_APP_INTEGRATION_GUIDE.md` |
| rf_finder 実装参照（MiddleWare） | `/Users/satoshi/rf_finder/apps/accounts/middleware.py` |
| rf_finder 実装参照（UserProfile） | `/Users/satoshi/rf_finder/apps/accounts/models.py` |
| svr 要件定義 | `docs/01_REQUIREMENTS_v7.md` |
| svr Django 実装テンプレート | `docs/07_DJANGO_IMPLEMENTATION_TEMPLATE_v3.md` |
| svr Docker 本番テンプレート | `docs/08_DOCKER_PRODUCTION_TEMPLATE_v3.md` |

---

## 10. 次のステップ（別フェーズ）

JWT 連携が完成したら、以下の順序で業務ロジックを実装する：

```
Week 1: Django/Docker/MySQL 基盤構築（本ファイルの作業）← 完了予定
Week 2: apps/performances/ コアモデル + テンプレート展開（1〜9工程）
Week 3: ダブルブッキング防止（人員・車輌 AssignmentService）
Week 4: 単価・原価管理 + 乖離分析（FreelanceRateService）
Week 5: LockService + スナップショット確定
Week 6: PDF 帳票出力
Week 7: UI ブラッシュアップ + ダッシュボード
Week 8: 本番デプロイ + SaaS 連携（freee/board）
```

詳細: `docs/10_IMPLEMENTATION_ROADMAP_8WEEKS_v4.md` 参照。
